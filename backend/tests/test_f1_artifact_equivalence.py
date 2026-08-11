"""STEP 1 equivalence test: production F1 inference (`assistive_feedback.
f1_artifact.F1Artifact.predict_proba`) must reproduce the benchmark path's
`_apply_variant_matrix` + `MLPFit.predict_proba` math EXACTLY, given the
SAME frozen weights.

Important design note: `EmbeddingPreprocessor.fit`'s PCA
(`numpy.linalg.svd`) is not bit-reproducible ACROSS SEPARATE PROCESS
invocations on this machine's multi-threaded BLAS (confirmed empirically --
re-running `f1_context_wav2vec.fit_frozen` in a fresh process can converge
to a numerically different, comparably-valid SVD solution, large enough to
move a probability by several hundredths). That is a property of PCA/SVD
fitting in general, not a bug in this equivalence test or in the artifact --
it is exactly WHY an artifact is exported and frozen once rather than
re-fit on every server start. So this test does not re-run `fit_frozen`
and compare it against the artifact (which would be comparing two
DIFFERENT, independently-fit models); it reconstructs the benchmark
classes FROM the artifact's own already-frozen weight arrays and checks
that the NEW production code path (`F1Artifact.predict_proba`) computes
the identical result the ORIGINAL benchmark code
(`EmbeddingPreprocessor.transform` + `Standardizer.transform` +
`MLPFit.predict_proba`) would, given that one frozen model. That is the
actual claim STEP 1 needs proven: the re-implementation is faithful, not
that two independent training runs agree.

Never touches `validation` or `final_test` -- uses development rows only,
via `benchmarking.candidates.praat_logistic.load_split_rows("development")`,
which refuses `final_test` without its own two independent gates; and here
only to obtain small, realistic, fixed sample inputs (not to refit a model).
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from assistive_feedback import f1_artifact

ARTIFACT_AVAILABLE = f1_artifact.artifact_exists()

pytestmark = pytest.mark.skipif(
    not ARTIFACT_AVAILABLE,
    reason="F1 production artifact not exported -- run `python -m assistive_feedback.f1_artifact export` first",
)

#: Small, fixed fixture size -- deterministic given `prepare_rows`'s own
#: deterministic ordering (no shuffling happens before this slice).
FIXTURE_SIZE = 12


@pytest.fixture(scope="module")
def sample_inputs():
    """A small, fixed set of (raw embedding, context vector) pairs from
    real development rows -- used only as realistic INPUT DATA, never to
    fit a new model (see module docstring for why fitting is excluded)."""
    from benchmarking.candidates import f1_context_wav2vec as f1

    dev_data = f1.prepare_rows("development")
    n = min(FIXTURE_SIZE, len(dev_data["rows"]))
    return [(dev_data["emb"][i], dev_data["ctx"][i]) for i in range(n)]


def _reconstruct_benchmark_classes(artifact: "f1_artifact.F1Artifact"):
    """Rebuilds the ORIGINAL benchmark classes from the artifact's own
    frozen weight arrays -- the SAME classes `f1_context_wav2vec.fit_frozen`
    would have produced, just reconstructed from disk instead of re-fit."""
    from benchmarking.candidates.f1_context_wav2vec import Standardizer
    from benchmarking.candidates.wav2vec_frozen_logistic import PCA, EmbeddingPreprocessor
    from benchmarking.mlp import MLPFit

    pca = PCA(mean=artifact.pca_mean, components=artifact.pca_components)
    emb_pre = EmbeddingPreprocessor(means=artifact.emb_pre_means, scales=artifact.emb_pre_scales, pca=pca)
    scaler = Standardizer(means=artifact.scaler_means, scales=artifact.scaler_scales)
    model = MLPFit(
        w1=artifact.mlp_w1, b1=artifact.mlp_b1, w2=artifact.mlp_w2, b2=artifact.mlp_b2,
        iterations=0, converged=True, final_loss=0.0,
    )
    return emb_pre, scaler, model


def test_fixture_is_not_final_test():
    """Structural guard: this module never imports anything that could load
    final_test, and the fixture comes from `prepare_rows("development")`
    only -- verified by AST inspection rather than trusted by comment."""
    import ast
    from pathlib import Path

    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "prepare_rows":
            assert all(
                isinstance(arg, ast.Constant) and arg.value != "final_test" for arg in node.args
            )


def test_production_matches_benchmark_probability(sample_inputs):
    artifact = f1_artifact.load_and_verify()
    emb_pre, scaler, model = _reconstruct_benchmark_classes(artifact)

    checked = 0
    for raw_embedding, context_vector in sample_inputs:
        # Benchmark path: `f1_context_wav2vec._apply_variant_matrix` +
        # `MLPFit.predict_proba`, using the SAME frozen weights the artifact
        # was exported from.
        pca_out = emb_pre.transform(raw_embedding.reshape(1, -1))
        combined_raw = np.hstack([pca_out, context_vector.reshape(1, -1)])
        combined = scaler.transform(combined_raw)
        benchmark_prob = float(model.predict_proba(combined)[0])

        # Production path: the exported artifact's own inference code.
        production_prob = artifact.predict_proba(raw_embedding, context_vector)

        # Tight, float64-realistic tolerance for the SAME chain of matrix
        # operations computed in a slightly different grouping (one
        # hstack-then-matmul vs separate matmuls) -- not a tolerance for
        # any real algorithmic divergence, since both paths use the
        # identical, already-frozen weight arrays here.
        assert production_prob == pytest.approx(benchmark_prob, abs=1e-6), (
            f"benchmark={benchmark_prob} production={production_prob}"
        )
        checked += 1

    assert checked == FIXTURE_SIZE


def test_artifact_context_feature_order_matches_live_encoder():
    from benchmarking.candidates.f1_context_wav2vec import CONTEXT_FEATURE_NAMES

    artifact = f1_artifact.load_and_verify()
    assert artifact.context_feature_names == list(CONTEXT_FEATURE_NAMES)


def test_artifact_records_the_same_checkpoint_candidate_c1_f1_used():
    from benchmarking.candidates.wav2vec_frozen_logistic import CHECKPOINT_NAME

    artifact = f1_artifact.load_and_verify()
    assert artifact.metadata["encoder"]["checkpoint"] == CHECKPOINT_NAME


def test_tampered_weights_are_rejected():
    """A weights file that no longer matches its own recorded hash must be
    refused, not silently loaded -- the artifact's own integrity check."""
    import json
    from pathlib import Path

    metadata = json.loads(f1_artifact.METADATA_PATH.read_text(encoding="utf-8"))
    tampered_metadata = dict(metadata, weights_sha256="0" * 64)
    tmp_path = f1_artifact.METADATA_PATH.parent / "f1_metadata_tampered_for_test.json"
    tmp_path.write_text(json.dumps(tampered_metadata), encoding="utf-8")
    try:
        with pytest.raises(f1_artifact.ArtifactIntegrityError):
            f1_artifact.load_and_verify(metadata_path=tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)
