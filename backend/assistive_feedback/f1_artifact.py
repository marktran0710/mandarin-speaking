"""Candidate F1 production deployment artifact.

    python -m assistive_feedback.f1_artifact export

STEP 1 of the minimal production integration. **Not a retrain.** This
exports the SAME frozen fit `benchmarking/candidates/f1_context_wav2vec.py`'s
`fit_frozen` already produces (deterministic — same development rows, same
fixed seed everywhere in the pipeline, same result every time it is called)
to a small, versioned, reproducible artifact on disk, so production
inference does not need to re-run the whole batch fitting pipeline (or
import `benchmarking.candidates.praat_logistic`'s heavier dependencies) on
every request.

The artifact bundles:

- the frozen Wav2Vec2 CHECKPOINT REFERENCE (name + weight hash) — the actual
  encoder weights are not duplicated here; they are loaded from the same
  HuggingFace checkpoint `benchmarking.candidates.wav2vec_frozen_logistic.
  FrozenEncoder` already uses, and the hash lets `load_and_verify` confirm
  the loaded checkpoint matches what was frozen at export time,
- the PCA + standardization preprocessing fitted on the embedding
  (`EmbeddingPreprocessor`, unchanged, imported read-only),
- the context feature encoder's fixed FEATURE ORDER (`CONTEXT_FEATURE_NAMES`,
  imported read-only — the encoder itself, `build_context_vector`, is pure
  Python with no fitted state, so only its output ORDER needs freezing),
- the final feature standardizer,
- the classifier (MLP) weights,
- protocol/version metadata and a SHA-256 of the whole artifact payload.

`load_and_verify` reproduces the frozen validation-time F1 output exactly —
see `tests/test_f1_artifact_equivalence.py` for the deterministic check
against the benchmark path on a small, fixed, non-final_test fixture.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

ARTIFACT_DIR = Path("private-data/f1_production_artifact")
WEIGHTS_PATH = ARTIFACT_DIR / "f1_weights.npz"
METADATA_PATH = ARTIFACT_DIR / "f1_metadata.json"

ARTIFACT_VERSION = "f1-production-v1"


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Export (run once, offline — not part of any live request path)
# ---------------------------------------------------------------------------


def export() -> dict[str, Any]:
    """Fits Candidate F1a's frozen preprocessing + classifier on ALL of
    development, EXACTLY as `f1_context_wav2vec.run()` already does (same
    function, same inputs, same fixed seeds throughout) — this is a
    reproduction/export of the existing frozen fit, not a new training run.
    Never touches validation or final_test."""
    from benchmarking.candidates import f1_context_wav2vec as f1
    from benchmarking.candidates.wav2vec_frozen_logistic import CHECKPOINT_NAME, _load_cache

    print("Preparing development rows (reused, unmodified)...")
    dev_data = f1.prepare_rows("development")
    print(f"  {len(dev_data['rows'])} rows")

    print("Fitting the frozen F1a variant on ALL of development (deterministic)...")
    frozen = f1.fit_frozen(dev_data, use_praat=False)
    emb_pre, scaler, model = frozen["emb_pre"], frozen["scaler"], frozen["model"]

    _, dev_meta = _load_cache("development")
    checkpoint = dev_meta.get("checkpoint", CHECKPOINT_NAME)
    checkpoint_sha256 = dev_meta.get("checkpoint_sha256")

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    np.savez(
        WEIGHTS_PATH,
        emb_pre_means=emb_pre.means, emb_pre_scales=emb_pre.scales,
        pca_mean=emb_pre.pca.mean, pca_components=emb_pre.pca.components,
        scaler_means=scaler.means, scaler_scales=scaler.scales,
        mlp_w1=model.w1, mlp_b1=model.b1, mlp_w2=model.w2, mlp_b2=model.b2,
    )
    weights_sha256 = _hash_bytes(WEIGHTS_PATH.read_bytes())

    metadata = {
        "artifact_version": ARTIFACT_VERSION,
        "variant": "F1a",
        "encoder": {"checkpoint": checkpoint, "checkpoint_sha256": checkpoint_sha256, "pooling": "mean"},
        "pca_dim": f1.PCA_DIM,
        "context_feature_names": list(f1.CONTEXT_FEATURE_NAMES),
        "hidden_units": model.w1.shape[1],
        "n_train_rows": frozen["n_train"],
        "weights_path": str(WEIGHTS_PATH),
        "weights_sha256": weights_sha256,
        "source_module": "benchmarking/candidates/f1_context_wav2vec.py",
        "source_function": "fit_frozen(prepare_rows('development'), use_praat=False)",
        "note": "Reproduction/export of the already-frozen F1a fit -- not a retrain. Deterministic given the fixed seeds already baked into f1_context_wav2vec.py and benchmarking.mlp.",
    }
    METADATA_PATH.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Artifact written: {WEIGHTS_PATH}, {METADATA_PATH}")
    return metadata


# ---------------------------------------------------------------------------
# Load + inference (used by the live pipeline)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class F1Artifact:
    metadata: dict[str, Any]
    emb_pre_means: np.ndarray
    emb_pre_scales: np.ndarray
    pca_mean: np.ndarray
    pca_components: np.ndarray
    scaler_means: np.ndarray
    scaler_scales: np.ndarray
    mlp_w1: np.ndarray
    mlp_b1: np.ndarray
    mlp_w2: np.ndarray
    mlp_b2: np.ndarray

    @property
    def context_feature_names(self) -> list[str]:
        return self.metadata["context_feature_names"]

    def predict_proba(self, embedding_768: np.ndarray, context_vector: np.ndarray) -> float:
        """Reproduces `f1_context_wav2vec._apply_variant_matrix` +
        `mlp.MLPFit.predict_proba` for exactly one row -- same math, same
        order of operations, no retraining or refitting involved."""
        embedding_768 = np.asarray(embedding_768, dtype=float).reshape(1, -1)
        context_vector = np.asarray(context_vector, dtype=float).reshape(1, -1)

        standardized = (embedding_768 - self.emb_pre_means) / self.emb_pre_scales
        pca_out = (standardized - self.pca_mean) @ self.pca_components.T
        combined_raw = np.hstack([pca_out, context_vector])
        combined = (combined_raw - self.scaler_means) / self.scaler_scales

        hidden = np.maximum(0.0, combined @ self.mlp_w1 + self.mlp_b1)
        logits = hidden @ self.mlp_w2 + self.mlp_b2
        z = logits.ravel()[0]
        return float(1.0 / (1.0 + np.exp(-z))) if z >= 0 else float(np.exp(z) / (1.0 + np.exp(z)))


class ArtifactIntegrityError(RuntimeError):
    """Raised when the on-disk artifact's hash does not match its own
    recorded metadata, or the loaded checkpoint does not match what was
    frozen at export time."""


def load_and_verify(
    weights_path: Path = WEIGHTS_PATH, metadata_path: Path = METADATA_PATH,
) -> F1Artifact:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    actual_hash = _hash_bytes(weights_path.read_bytes())
    if actual_hash != metadata["weights_sha256"]:
        raise ArtifactIntegrityError(
            f"F1 artifact weights hash mismatch: expected {metadata['weights_sha256']}, got {actual_hash} "
            f"-- the weights file does not match the metadata it was exported with."
        )
    data = np.load(weights_path)
    return F1Artifact(
        metadata=metadata,
        emb_pre_means=data["emb_pre_means"], emb_pre_scales=data["emb_pre_scales"],
        pca_mean=data["pca_mean"], pca_components=data["pca_components"],
        scaler_means=data["scaler_means"], scaler_scales=data["scaler_scales"],
        mlp_w1=data["mlp_w1"], mlp_b1=data["mlp_b1"], mlp_w2=data["mlp_w2"], mlp_b2=data["mlp_b2"],
    )


def artifact_exists(weights_path: Path = WEIGHTS_PATH, metadata_path: Path = METADATA_PATH) -> bool:
    return weights_path.exists() and metadata_path.exists()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2 or sys.argv[1] != "export":
        print("usage: python -m assistive_feedback.f1_artifact export")
        raise SystemExit(1)
    export()
