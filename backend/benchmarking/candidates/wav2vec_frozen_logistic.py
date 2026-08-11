"""CANDIDATE C1 — frozen Wav2Vec2 embeddings + a simple classifier.

    python -m benchmarking.candidates.wav2vec_frozen_logistic

Research question: does a richer, learned speech representation (frozen
Wav2Vec2 hidden states) discriminate OMPAL expert-rated correct vs incorrect
Mandarin tone production substantially better than the current hand-crafted
Praat contour heuristic (Baseline A) or the Praat-feature logistic baseline
(Candidate B1)?

Gated on `benchmarking/results/candidate_c_wav2vec_provenance_audit.md`,
which classified the existing `pronunciation/wav2vec_tone/` encoder as
**B: ENCODER CLEAN, CLASSIFIER CONTAMINATED** — the frozen checkpoint itself
was never fine-tuned on OMPAL or anything else, but an existing downstream
classifier built on it *was* fit and selected using OMPAL labels. This module
therefore reuses the checkpoint (via
`pronunciation.wav2vec_tone.extract_embeddings.FrozenWav2Vec2`, the same
class the audit verified freezes its own weights at construction) purely as
a forward-pass feature extractor, and fits a brand-new classifier from
scratch on the *current* development/validation split — it never imports,
loads, or is informed by `MODEL_A_wav2vec2`, `produced_tone_fusion_nested`,
or any other artifact under `pronunciation/wav2vec_tone/data/`.

FINAL_TEST IS NOT TOUCHED ANYWHERE IN THIS MODULE. Row loading is delegated
entirely to `benchmarking.candidates.praat_logistic.load_split_rows`, which
already refuses the `final_test` partition without both of its independent
gates — this module never passes `unlock_final_test=True`, so it inherits
that guarantee rather than re-implementing (and risking diverging from) it.

Pooling: mean-pooling over time, per the task's pre-specified default. This
also matches the *original*, pre-OMPAL documented rationale in
`pronunciation/wav2vec_tone/extract_embeddings.py` ("Mean-pooling over time
collapses the utterance to a single vector") — a design predating the later,
OMPAL-informed mean-vs-temporal3 comparison in `develop_models.py`. Only
mean pooling is used here; temporal3 is not tried, per the task's "do not
try many pooling methods after seeing validation results" and to avoid any
reliance on that later, OMPAL-tainted comparison's conclusion.

Dimension control: 768-dim embeddings against ~250-400 incorrect-label
examples per tone (see `candidate_b_praat_logistic.md` §4 for the per-tone
counts, unchanged here since it's the same corpus) fails the conventional
~10-events-per-predictor guideline by more than an order of magnitude
(768 predictors vs. as few as ~250 minority events -- roughly 0.3 events per
predictor). Per the task's STEP 4, direct high-dimensional logistic
regression on raw embeddings is therefore not attempted; this module goes
straight to option B (standardize, then PCA, then L2-penalized logistic
regression), with the PCA dimensionality chosen from a small, pre-specified
grid via development-only grouped cross-validation, frozen before validation
is ever touched (`select_pca_dimension`).
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from benchmarking.baseline_a import evaluate as evaluate_baseline_a
from benchmarking.candidates.praat_logistic import (
    FinalTestLockedError,
    _group_by_tone,
    _labels,
    _pooled_metrics,
    _select_threshold,
    _usable,
    load_split_rows,
)
from benchmarking.logistic import fit as fit_logistic
from benchmarking.splits import grouped_kfold
from benchmarking.stats import binary_agreement, roc_auc

TONES = ("1", "2", "3", "4")

#: The one checkpoint this module will ever load — see the provenance audit,
#: §1. `FrozenWav2Vec2` itself falls back to `facebook/wav2vec2-base` if this
#: repo is unreachable; both are captured in the cache metadata either way.
CHECKPOINT_NAME = "TencentGameMate/chinese-wav2vec2-base"
EMBEDDING_DIM = 768
POOLING = "mean"
SAMPLE_RATE = 16000
#: ~25ms at 16kHz -- below this the encoder's convolutional stem cannot
#: produce even one output frame, so mean-pooling would be undefined.
MIN_SPAN_SAMPLES = 400

#: Where extracted embeddings are cached, keyed by (audio_id, syllable_index)
#: so repeated classifier experiments never re-run the encoder. This directory
#: is git-ignored (see backend/.gitignore's `private-data/` rule) because the
#: cache is a large binary derivative of private OMPAL audio.
CACHE_DIR = Path("private-data/wav2vec_embeddings_cache")

REPORT_PATH = Path("benchmarking/results/candidate_c_frozen_wav2vec.md")
PREDICTIONS_PATH = Path("benchmarking/results/candidate_c_validation_predictions.csv")

CV_FOLDS = 5
CV_SEED = 20260810  # same seed as the top-level speaker split and Candidate B1
L2 = 1.0  # matches Candidate B1; fixed, not searched

#: Pre-specified, small grid for the single shared PCA dimensionality (one
#: number, not one per tone -- keeps the search budget tiny). Chosen so the
#: largest candidate (50) still clears ~5 events per predictor against the
#: smallest tone's ~250 incorrect examples, and the smallest candidate (10)
#: is still large enough to carry more than a single principal axis of
#: variation. Frozen here, before `select_pca_dimension` is ever called.
PCA_DIM_GRID = (10, 20, 30, 50)

EXCLUDED_FROM_FEATURES = (
    "human ratings other than the target label (individual_rater_labels, "
    "human_accuracy, human_fluency, human_prosody)",
    "word identity (word, pinyin)",
    "speaker identity (speaker_id) — used only for CV grouping, never as a feature",
    "audio ID (audio_id)",
    "any Praat/acoustic feature from Candidate B1 — Candidate C1 evaluates the "
    "embedding representation on its own, not a fusion of the two",
)


# ---------------------------------------------------------------------------
# Frozen encoder
# ---------------------------------------------------------------------------


def _resolve_audio_path(raw_path: str) -> Path:
    """`diagnostics.py` writes `audio_path` with OS-native separators from
    whatever platform generated the CSV; normalise before joining so a run on
    a different OS still resolves it."""
    return Path(*raw_path.replace("\\", "/").split("/"))


def _hash_state_dict(model) -> str:
    """SHA-256 over every parameter tensor's name and bytes -- a concrete,
    reproducible fingerprint of the exact weights in use, stored in the cache
    metadata alongside the checkpoint name. Two runs against the same
    checkpoint always produce the same hash; a different checkpoint (or a
    fine-tuned copy of the same name) would not."""
    hasher = hashlib.sha256()
    for name, param in sorted(model.state_dict().items()):
        hasher.update(name.encode("utf-8"))
        hasher.update(param.detach().cpu().numpy().tobytes())
    return hasher.hexdigest()


class FrozenEncoder:
    """Thin wrapper around
    `pronunciation.wav2vec_tone.extract_embeddings.FrozenWav2Vec2` that adds
    span-level (rather than whole-file) mean-pooled embedding extraction.
    Reuses that class's own construction-time freeze assertion rather than
    re-implementing it -- see the provenance audit, §2."""

    def __init__(self, checkpoint: str = CHECKPOINT_NAME) -> None:
        from pronunciation.wav2vec_tone.extract_embeddings import FrozenWav2Vec2

        self._impl = FrozenWav2Vec2(checkpoint)
        if self._impl.trainable_parameters != 0:
            raise RuntimeError(
                f"{self._impl.trainable_parameters} wav2vec2 parameters are "
                "trainable; Candidate C1 requires the encoder fully frozen."
            )
        self.checkpoint = self._impl.model_name
        self.checkpoint_hash = _hash_state_dict(self._impl.model)

    def embed_span(self, audio_path: str, start_time: float, end_time: float) -> np.ndarray | None:
        """Mean-pooled hidden state over one syllable span, or None if the
        span is too short to produce any encoder output."""
        from pronunciation.wav2vec_tone.extract_embeddings import load_audio_16k_mono

        waveform = load_audio_16k_mono(_resolve_audio_path(audio_path))
        start_sample = max(0, int(round(start_time * SAMPLE_RATE)))
        end_sample = min(len(waveform), int(round(end_time * SAMPLE_RATE)))
        segment = waveform[start_sample:end_sample]
        if len(segment) < MIN_SPAN_SAMPLES:
            return None
        inputs = self._impl.processor(segment, sampling_rate=SAMPLE_RATE, return_tensors="pt")
        with self._impl._torch.no_grad():
            output = self._impl.model(**inputs)
        hidden = output.last_hidden_state[0].numpy()
        return hidden.mean(axis=0).astype(np.float32)


# ---------------------------------------------------------------------------
# Embedding cache
# ---------------------------------------------------------------------------


def _row_key(row: dict[str, Any]) -> str:
    return f"{row['audio_id']}::{row.get('syllable_index', '0')}"


def _cache_paths(split_name: str) -> tuple[Path, Path]:
    return (
        CACHE_DIR / f"{split_name}_embeddings.npz",
        CACHE_DIR / f"{split_name}_embeddings_meta.json",
    )


def _load_cache(split_name: str) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    npz_path, meta_path = _cache_paths(split_name)
    vectors: dict[str, np.ndarray] = {}
    if npz_path.exists():
        # allow_pickle=True: the only object-dtype array here is our own
        # `keys` (a plain string array), never untrusted external input.
        stored = np.load(npz_path, allow_pickle=True)
        for key, vector in zip(stored["keys"], stored["embeddings"]):
            vectors[str(key)] = vector
    metadata: dict[str, Any] = {}
    if meta_path.exists():
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    return vectors, metadata


def _save_cache(
    split_name: str,
    vectors: dict[str, np.ndarray],
    row_metadata: dict[str, dict[str, Any]],
    encoder: FrozenEncoder,
) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    npz_path, meta_path = _cache_paths(split_name)
    keys = sorted(vectors)
    embeddings = np.vstack([vectors[k] for k in keys]) if keys else np.zeros((0, EMBEDDING_DIM))
    np.savez_compressed(npz_path, keys=np.array(keys, dtype=object), embeddings=embeddings)
    payload = {
        "checkpoint": encoder.checkpoint,
        "checkpoint_sha256": encoder.checkpoint_hash,
        "encoder_frozen": True,
        "pooling": POOLING,
        "split": split_name,
        "embedding_dim": EMBEDDING_DIM,
        "n_cached": len(keys),
        # Per-key provenance: speaker, audio ID, syllable span, expected tone,
        # and which split each embedding belongs to -- STEP 3's metadata
        # requirement.
        "rows": {k: row_metadata[k] for k in keys if k in row_metadata},
    }
    meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_embeddings(
    rows: Sequence[dict[str, Any]],
    split_name: str,
    *,
    encoder: FrozenEncoder | None = None,
    save_every: int = 1000,
) -> tuple[np.ndarray, np.ndarray, int, FrozenEncoder | None]:
    """Embeddings aligned 1:1 with `rows`. Reuses (and extends) an on-disk
    cache keyed by (audio_id, syllable_index), so re-running this against the
    same rows never re-invokes the encoder. Returns
    (matrix, valid_mask, n_missing, encoder) -- `encoder` is created lazily
    only if the cache doesn't already cover every row, and is returned so a
    second call (e.g. for validation right after development) can reuse the
    already-loaded model instead of paying the ~5s load cost twice.
    """
    vectors, old_meta = _load_cache(split_name)
    all_row_metadata: dict[str, dict[str, Any]] = dict(old_meta.get("rows", {})) if old_meta else {}

    matrix = np.full((len(rows), EMBEDDING_DIM), np.nan, dtype=np.float32)
    missing = 0
    since_save = 0
    dirty = False
    active_encoder = encoder

    for i, row in enumerate(rows):
        key = _row_key(row)
        all_row_metadata[key] = {
            "audio_id": row["audio_id"],
            "speaker_id": row["speaker_id"],
            "expected_tone": row["expected_tone"],
            "syllable_start_time": row.get("syllable_start_time"),
            "syllable_end_time": row.get("syllable_end_time"),
            "split": split_name,
        }
        cached = vectors.get(key)
        if cached is not None:
            matrix[i] = cached
            continue

        start, end = row.get("syllable_start_time"), row.get("syllable_end_time")
        if start in (None, "", "NA") or end in (None, "", "NA"):
            missing += 1
            continue

        if active_encoder is None:
            active_encoder = FrozenEncoder()

        vector = active_encoder.embed_span(row["audio_path"], float(start), float(end))
        if vector is None:
            missing += 1
            continue

        vectors[key] = vector
        matrix[i] = vector
        dirty = True
        since_save += 1
        if since_save >= save_every:
            _save_cache(split_name, vectors, all_row_metadata, active_encoder)
            since_save = 0
        if (i + 1) % 500 == 0:
            print(f"  [{split_name}] {i + 1}/{len(rows)} embedded ({missing} unusable so far)")

    if dirty:
        _save_cache(split_name, vectors, all_row_metadata, active_encoder)

    valid_mask = ~np.isnan(matrix).any(axis=1)
    return matrix, valid_mask, missing, active_encoder


def _group_rows_and_embeddings_by_tone(
    rows: list[dict[str, Any]], matrix: np.ndarray
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, np.ndarray]]:
    by_tone_rows: dict[str, list[dict[str, Any]]] = {tone: [] for tone in TONES}
    by_tone_idx: dict[str, list[int]] = {tone: [] for tone in TONES}
    for i, row in enumerate(rows):
        tone = row["expected_tone"]
        if tone in by_tone_rows:
            by_tone_rows[tone].append(row)
            by_tone_idx[tone].append(i)
    by_tone_matrix = {
        tone: (matrix[idx] if idx else np.zeros((0, EMBEDDING_DIM), dtype=np.float32))
        for tone, idx in by_tone_idx.items()
    }
    return by_tone_rows, by_tone_matrix


# ---------------------------------------------------------------------------
# Preprocessing: standardize, then PCA -- both fit on training data only
# ---------------------------------------------------------------------------


class PCA:
    """Minimal, dependency-free PCA via SVD (no scikit-learn -- same
    discipline as `benchmarking.logistic`)."""

    def __init__(self, mean: np.ndarray, components: np.ndarray) -> None:
        self.mean = mean
        self.components = components  # shape (n_components, n_features)

    @classmethod
    def fit(cls, features: np.ndarray, n_components: int) -> "PCA":
        mean = features.mean(axis=0)
        centered = features - mean
        _, _, vt = np.linalg.svd(centered, full_matrices=False)
        return cls(mean=mean, components=vt[:n_components])

    def transform(self, features: np.ndarray) -> np.ndarray:
        return (features - self.mean) @ self.components.T


class EmbeddingPreprocessor:
    """Standardize (fit on train only) then PCA (fit on the standardized
    train only). Mirrors Candidate B1's `Preprocessor` discipline: fit once,
    applied unchanged to whatever is transformed next, never re-fit on
    validation. No imputation step -- rows with no embedding are excluded
    upstream (`build_embeddings`'s `valid_mask`), not imputed, since a
    missing embedding means the encoder produced nothing at all, not a
    single missing scalar."""

    def __init__(self, means: np.ndarray, scales: np.ndarray, pca: PCA) -> None:
        self.means = means
        self.scales = scales
        self.pca = pca

    @classmethod
    def fit(cls, raw_features: np.ndarray, n_components: int) -> "EmbeddingPreprocessor":
        means = raw_features.mean(axis=0)
        scales = raw_features.std(axis=0)
        scales = np.where(scales < 1e-9, 1.0, scales)
        standardized = (raw_features - means) / scales
        pca = PCA.fit(standardized, n_components)
        return cls(means=means, scales=scales, pca=pca)

    def transform(self, raw_features: np.ndarray) -> np.ndarray:
        standardized = (raw_features - self.means) / self.scales
        return self.pca.transform(standardized)


# ---------------------------------------------------------------------------
# Development grouped cross-validation (shared across the PCA-dimension grid)
# ---------------------------------------------------------------------------


def run_grouped_cv(
    dev_rows_by_tone: dict[str, list[dict[str, Any]]],
    dev_embeddings_by_tone: dict[str, np.ndarray],
    *,
    pca_dim: int,
    k: int = CV_FOLDS,
    seed: int = CV_SEED,
) -> dict[str, Any]:
    """Speaker-grouped CV within development, per tone, for one candidate PCA
    dimensionality. Same fold partition (by speaker, not re-randomized per
    tone) as Candidate B1's `run_grouped_cv`, same seed, so "fold N" means
    the same held-out speakers as it did there."""
    all_dev_speakers = sorted({row["speaker_id"] for rows in dev_rows_by_tone.values() for row in rows})
    folds = grouped_kfold(all_dev_speakers, k=k, seed=seed)

    per_tone_oof: dict[str, dict[str, np.ndarray]] = {}
    per_tone_fold_metrics: dict[str, list[dict[str, Any]]] = {tone: [] for tone in TONES}

    for tone in TONES:
        rows = dev_rows_by_tone[tone]
        raw_features = dev_embeddings_by_tone[tone]
        labels = _labels(rows)
        speaker_ids = np.array([row["speaker_id"] for row in rows])

        oof_prob = np.full(len(rows), np.nan)
        for fold_index, (train_speakers, held_out_speakers) in enumerate(folds):
            train_mask = np.isin(speaker_ids, train_speakers)
            test_mask = np.isin(speaker_ids, held_out_speakers)
            if train_mask.sum() == 0 or test_mask.sum() == 0:
                continue
            if len(set(labels[train_mask])) < 2:
                continue

            n_components = int(min(pca_dim, train_mask.sum() - 1, raw_features.shape[1]))
            preprocessor = EmbeddingPreprocessor.fit(raw_features[train_mask], n_components)
            model = fit_logistic(
                preprocessor.transform(raw_features[train_mask]), labels[train_mask], l2=L2
            )
            test_prob = model.predict_proba(preprocessor.transform(raw_features[test_mask]))
            oof_prob[test_mask] = test_prob

            fold_auc = roc_auc(list(test_prob), list(labels[test_mask].astype(bool)))
            per_tone_fold_metrics[tone].append({
                "fold": fold_index,
                "n_train": int(train_mask.sum()),
                "n_test": int(test_mask.sum()),
                "n_components": n_components,
                "auc": fold_auc,
                "converged": model.converged,
            })

        per_tone_oof[tone] = {"probabilities": oof_prob, "labels": labels}

    return {"folds": folds, "oof": per_tone_oof, "fold_metrics": per_tone_fold_metrics}


def select_pca_dimension(
    dev_rows_by_tone: dict[str, list[dict[str, Any]]],
    dev_embeddings_by_tone: dict[str, np.ndarray],
) -> tuple[int, list[dict[str, Any]], dict[str, Any]]:
    """The one, pre-specified dimension-selection rule: the grid point in
    `PCA_DIM_GRID` maximizing pooled out-of-fold ROC AUC across all four
    tones, computed entirely from development grouped-CV. Validation is not
    referenced anywhere in this function -- see
    `tests/test_candidate_c.py::TestNoValidationLeakage` for the structural
    check that enforces this."""
    grid_results: list[dict[str, Any]] = []
    best_dim, best_auc, best_cv = PCA_DIM_GRID[0], -1.0, None

    for dim in PCA_DIM_GRID:
        cv = run_grouped_cv(dev_rows_by_tone, dev_embeddings_by_tone, pca_dim=dim)
        all_prob = np.concatenate([cv["oof"][t]["probabilities"] for t in TONES])
        all_label = np.concatenate([cv["oof"][t]["labels"] for t in TONES])
        valid = ~np.isnan(all_prob)
        auc = (
            roc_auc(list(all_prob[valid]), list(all_label[valid].astype(bool)))
            if valid.any()
            else None
        )
        grid_results.append({"pca_dim": dim, "pooled_dev_cv_auc": auc})
        if auc is not None and auc > best_auc:
            best_dim, best_auc, best_cv = dim, auc, cv

    if best_cv is None:  # every candidate produced no scorable OOF predictions
        best_cv = run_grouped_cv(dev_rows_by_tone, dev_embeddings_by_tone, pca_dim=best_dim)

    return best_dim, grid_results, best_cv


# ---------------------------------------------------------------------------
# Freeze, then evaluate validation exactly once
# ---------------------------------------------------------------------------


def fit_frozen_models(
    dev_rows_by_tone: dict[str, list[dict[str, Any]]],
    dev_embeddings_by_tone: dict[str, np.ndarray],
    pca_dim: int,
) -> dict[str, dict[str, Any]]:
    """Candidate C1 itself: one standardize+PCA preprocessor and one logistic
    fit per tone, trained on ALL of development at the frozen PCA
    dimensionality. Nothing downstream may refit on validation."""
    frozen: dict[str, dict[str, Any]] = {}
    for tone in TONES:
        raw_features = dev_embeddings_by_tone[tone]
        labels = _labels(dev_rows_by_tone[tone])
        n_components = int(min(pca_dim, raw_features.shape[0] - 1, raw_features.shape[1]))
        preprocessor = EmbeddingPreprocessor.fit(raw_features, n_components)
        model = fit_logistic(preprocessor.transform(raw_features), labels, l2=L2)
        frozen[tone] = {
            "preprocessor": preprocessor,
            "model": model,
            "n_train": len(labels),
            "n_components": n_components,
        }
    return frozen


def evaluate_validation_once(
    frozen: dict[str, dict[str, Any]],
    thresholds: dict[str, float],
    val_rows_by_tone: dict[str, list[dict[str, Any]]],
    val_embeddings_by_tone: dict[str, np.ndarray],
) -> dict[str, Any]:
    """The single, frozen application of Candidate C1 to validation."""
    per_tone: dict[str, Any] = {}
    predictions: list[dict[str, Any]] = []
    all_prob: list[float] = []
    all_label: list[float] = []
    all_pred: list[bool] = []

    for tone in TONES:
        rows = val_rows_by_tone[tone]
        if not rows:
            per_tone[tone] = {"n": 0}
            continue
        raw_features = val_embeddings_by_tone[tone]
        labels = _labels(rows)
        preprocessor: EmbeddingPreprocessor = frozen[tone]["preprocessor"]
        model = frozen[tone]["model"]
        probabilities = model.predict_proba(preprocessor.transform(raw_features))
        threshold = thresholds[tone]
        predicted = probabilities >= threshold

        metrics = binary_agreement(list(predicted), list(labels.astype(bool)))
        metrics["auc"] = roc_auc(list(probabilities), list(labels.astype(bool)))
        metrics["threshold"] = threshold
        per_tone[tone] = metrics

        all_prob.extend(probabilities.tolist())
        all_label.extend(labels.tolist())
        all_pred.extend(predicted.tolist())

        for row, prob, pred in zip(rows, probabilities, predicted):
            predictions.append({
                "audio_id": row["audio_id"],
                "speaker_id": row["speaker_id"],
                "word": row["word"],
                "expected_tone": tone,
                "human_majority_tone_correct": row["human_majority_tone_correct"],
                "candidate_c_probability": round(float(prob), 4),
                "candidate_c_threshold": threshold,
                "candidate_c_predicted_correct": int(bool(pred)),
                "baseline_a_system_tone_correct": row["system_tone_correct"],
                "baseline_a_system_character_score": row["system_character_score"],
            })

    overall = binary_agreement(all_pred, [bool(v) for v in all_label])
    overall["auc"] = roc_auc(all_prob, [bool(v) for v in all_label]) if all_prob else None
    return {"overall": overall, "by_tone": per_tone, "predictions": predictions}


def write_predictions_csv(predictions: list[dict[str, Any]], path: Path = PREDICTIONS_PATH) -> int:
    fieldnames = [
        "audio_id", "speaker_id", "word", "expected_tone",
        "human_majority_tone_correct", "candidate_c_probability",
        "candidate_c_threshold", "candidate_c_predicted_correct",
        "baseline_a_system_tone_correct", "baseline_a_system_character_score",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(predictions)
    return len(predictions)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run() -> dict[str, Any]:
    dev_rows_raw = load_split_rows("development")
    val_rows_raw = load_split_rows("validation")
    dev_rows, dev_excluded_no_features = _usable(dev_rows_raw)
    val_rows, val_excluded_no_features = _usable(val_rows_raw)

    print(f"Embedding development ({len(dev_rows)} rows)...")
    dev_matrix, dev_valid_mask, dev_missing_embeddings, encoder = build_embeddings(dev_rows, "development")
    print(f"Embedding validation ({len(val_rows)} rows)...")
    val_matrix, val_valid_mask, val_missing_embeddings, encoder = build_embeddings(
        val_rows, "validation", encoder=encoder
    )

    dev_rows = [row for row, ok in zip(dev_rows, dev_valid_mask) if ok]
    dev_matrix = dev_matrix[dev_valid_mask]
    val_rows = [row for row, ok in zip(val_rows, val_valid_mask) if ok]
    val_matrix = val_matrix[val_valid_mask]

    dev_by_tone, dev_embeddings_by_tone = _group_rows_and_embeddings_by_tone(dev_rows, dev_matrix)
    val_by_tone, val_embeddings_by_tone = _group_rows_and_embeddings_by_tone(val_rows, val_matrix)

    pca_dim, pca_grid_results, cv = select_pca_dimension(dev_by_tone, dev_embeddings_by_tone)

    thresholds = {
        tone: _select_threshold(cv["oof"][tone]["probabilities"], cv["oof"][tone]["labels"])
        for tone in TONES
    }
    cv_metrics_per_tone = {
        tone: _pooled_metrics(cv["oof"][tone]["probabilities"], cv["oof"][tone]["labels"], thresholds[tone])
        for tone in TONES
    }
    all_oof_prob = np.concatenate([cv["oof"][t]["probabilities"] for t in TONES])
    all_oof_label = np.concatenate([cv["oof"][t]["labels"] for t in TONES])
    all_oof_pred = np.concatenate([cv["oof"][t]["probabilities"] >= thresholds[t] for t in TONES])
    valid = ~np.isnan(all_oof_prob)
    cv_overall = binary_agreement(list(all_oof_pred[valid]), list(all_oof_label[valid].astype(bool)))
    cv_overall["auc"] = roc_auc(list(all_oof_prob[valid]), list(all_oof_label[valid].astype(bool)))

    frozen = fit_frozen_models(dev_by_tone, dev_embeddings_by_tone, pca_dim)
    validation_result = evaluate_validation_once(frozen, thresholds, val_by_tone, val_embeddings_by_tone)

    baseline_dev = evaluate_baseline_a(dev_rows)
    baseline_val = evaluate_baseline_a(val_rows)
    baseline_dev_by_tone = {tone: evaluate_baseline_a(dev_by_tone[tone]) for tone in TONES}
    baseline_val_by_tone = {tone: evaluate_baseline_a(val_by_tone[tone]) for tone in TONES}

    n_predictions = write_predictions_csv(validation_result["predictions"])

    if encoder is not None:
        checkpoint, checkpoint_hash = encoder.checkpoint, encoder.checkpoint_hash
    else:
        # Every row was already cached, so build_embeddings never had to
        # construct an encoder -- fall back to the identity recorded in the
        # cache metadata from whichever run originally computed it.
        _, dev_meta = _load_cache("development")
        checkpoint = dev_meta.get("checkpoint", CHECKPOINT_NAME)
        checkpoint_hash = dev_meta.get("checkpoint_sha256")

    return {
        "checkpoint": checkpoint,
        "checkpoint_sha256": checkpoint_hash,
        "pooling": POOLING,
        "dev_excluded_no_features": dev_excluded_no_features,
        "val_excluded_no_features": val_excluded_no_features,
        "dev_excluded_no_embedding": dev_missing_embeddings,
        "val_excluded_no_embedding": val_missing_embeddings,
        "dev_n": len(dev_rows),
        "val_n": len(val_rows),
        "pca_dim": pca_dim,
        "pca_grid_results": pca_grid_results,
        "thresholds": thresholds,
        "cv_fold_metrics": cv["fold_metrics"],
        "cv_overall": cv_overall,
        "cv_by_tone": cv_metrics_per_tone,
        "validation_overall": validation_result["overall"],
        "validation_by_tone": validation_result["by_tone"],
        "baseline_dev": baseline_dev,
        "baseline_val": baseline_val,
        "baseline_dev_by_tone": baseline_dev_by_tone,
        "baseline_val_by_tone": baseline_val_by_tone,
        "n_predictions_written": n_predictions,
    }


if __name__ == "__main__":
    from benchmarking.candidates import report_wav2vec_frozen

    result = run()
    report_wav2vec_frozen.write_report(result)
    print(f"Predictions written to {PREDICTIONS_PATH} ({result['n_predictions_written']} rows)")
    print(f"Report written to {REPORT_PATH}")
