"""Candidate C1's guard rails: the final_test lock (inherited from Candidate
B1's loader), no speaker leakage in embedding-space CV, dev-only fitting for
both the standardize+PCA preprocessor and the PCA-dimension grid search, the
frozen-encoder invariant, checkpoint identity, and deterministic embedding
generation.

Most tests here use a `FakeEncoder` — deterministic, hash-derived vectors
with no real audio file or model load — so the guard-rail logic can be
verified in well under a second. The handful of tests that must touch the
real Wav2Vec2 checkpoint (frozen-parameter proof, checkpoint identity,
determinism of the *actual* forward pass) are isolated into
`TestRealEncoder` and share one module-scoped fixture so the ~5s model load
happens once, not per test.
"""
import csv
import hashlib
import os
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from benchmarking.candidates.praat_logistic import FinalTestLockedError
from benchmarking.candidates.wav2vec_frozen_logistic import (
    CHECKPOINT_NAME,
    EMBEDDING_DIM,
    EmbeddingPreprocessor,
    PCA,
    _group_rows_and_embeddings_by_tone,
    _row_key,
    build_embeddings,
    load_split_rows,
    run_grouped_cv,
    select_pca_dimension,
)
from benchmarking.splits import create_speaker_split, write_split

SPEAKERS = [f"SPEAKER02{i:03d}" for i in range(1, 21)]


class FakeEncoder:
    """No audio file, no torch, no transformers — a deterministic vector
    derived from (audio_path, start, end) via a seeded hash, so tests never
    need a real WAV file or the ~5s model load."""

    def __init__(self) -> None:
        self.checkpoint = "fake/test-checkpoint"
        self.checkpoint_hash = "deadbeef"
        self.calls = 0

    def embed_span(self, audio_path, start_time, end_time):
        self.calls += 1
        if end_time - start_time <= 0:
            return None
        seed = int(hashlib.sha256(f"{audio_path}:{start_time}:{end_time}".encode()).hexdigest(), 16) % (2**32)
        rng = np.random.default_rng(seed)
        return rng.normal(size=EMBEDDING_DIM).astype(np.float32)


def _toy_corpus(tmp_path, rng):
    split = create_speaker_split(SPEAKERS, ratios={"development": 0.6, "validation": 0.2, "final_test": 0.2})
    split_path = tmp_path / "split.json"
    write_split(split, split_path)

    csv_path = tmp_path / "diagnostics.csv"
    fieldnames = [
        "audio_id", "speaker_id", "expected_tone", "human_majority_tone_correct",
        "system_tone_correct", "system_character_score", "word", "syllable_index",
        "duration_seconds", "syllable_start_time", "syllable_end_time", "audio_path",
    ]
    rows = []
    all_speakers = split.development + split.validation + split.final_test
    for speaker in all_speakers:
        for j in range(15):
            start = round(rng.uniform(0, 1), 3)
            rows.append({
                "audio_id": f"{speaker}-{j}",
                "speaker_id": speaker,
                "expected_tone": str((j % 4) + 1),
                "human_majority_tone_correct": str(int(rng.uniform() < 0.7)),
                "system_tone_correct": str(int(rng.uniform() < 0.5)),
                "system_character_score": f"{rng.uniform(0, 100):.1f}",
                "word": "測",
                "syllable_index": str(j),
                "duration_seconds": "0.3",
                "syllable_start_time": f"{start:.3f}",
                "syllable_end_time": f"{start + 0.3:.3f}",
                "audio_path": f"fake/{speaker}/{speaker}-{j}.wav",
            })
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return split, split_path, csv_path


@pytest.fixture
def toy_corpus(tmp_path):
    return _toy_corpus(tmp_path, np.random.default_rng(0))


class TestFinalTestLockIsInherited:
    """Candidate C1 imports `load_split_rows` from Candidate B1 rather than
    re-implementing the guard — these tests confirm it's the same guarded
    function, not a lookalike that happens to share a name."""

    def test_is_literally_the_same_function_object_as_candidate_b(self):
        from benchmarking.candidates import praat_logistic

        assert load_split_rows is praat_logistic.load_split_rows

    def test_raises_without_any_unlock(self, toy_corpus):
        _split, split_path, csv_path = toy_corpus
        with pytest.raises(FinalTestLockedError):
            load_split_rows("final_test", diagnostics_csv=csv_path, split_path=split_path)

    def test_run_never_requests_an_unlock(self):
        """Checks bytecode-referenced names/constants, not source text --
        the module's own docstrings *describe* the guard using these exact
        strings, so a plain text search over the whole module would trip on
        its own documentation rather than on real usage."""
        from benchmarking.candidates.wav2vec_frozen_logistic import run

        code = run.__code__
        assert "unlock_final_test" not in code.co_names
        assert not any(
            isinstance(const, str) and "OMPAL_FINAL_TEST_UNLOCKED" in const
            for const in code.co_consts
        )


class TestPcaFitOnTrainOnly:
    def test_transform_uses_fitted_components_not_new_data(self):
        rng = np.random.default_rng(1)
        train = rng.normal(size=(50, 20))
        pca = PCA.fit(train, n_components=5)
        other = rng.normal(loc=100, scale=1, size=(10, 20))
        transformed = pca.transform(other)
        expected = (other - pca.mean) @ pca.components.T
        assert np.allclose(transformed, expected)

    def test_components_are_orthonormal(self):
        rng = np.random.default_rng(2)
        train = rng.normal(size=(60, 15))
        pca = PCA.fit(train, n_components=4)
        gram = pca.components @ pca.components.T
        assert np.allclose(gram, np.eye(4), atol=1e-6)

    def test_reduces_to_requested_dimensionality(self):
        rng = np.random.default_rng(3)
        train = rng.normal(size=(40, 30))
        pca = PCA.fit(train, n_components=7)
        assert pca.transform(train).shape == (40, 7)


class TestEmbeddingPreprocessorNeverRefits:
    def test_standardization_stats_come_from_train_not_from_new_data(self):
        rng = np.random.default_rng(4)
        train = rng.normal(loc=5, scale=2, size=(100, 30))
        preprocessor = EmbeddingPreprocessor.fit(train, n_components=6)
        other = rng.normal(loc=500, scale=50, size=(10, 30))
        transformed = preprocessor.transform(other)
        # If this had refit on `other`, the transformed mean would land near
        # zero; because it uses TRAIN's stats, it must not.
        assert not np.allclose(transformed.mean(), 0.0, atol=0.5)

    def test_constant_dimension_is_not_divided_by_near_zero(self):
        rng = np.random.default_rng(5)
        train = rng.normal(size=(50, 10))
        train[:, 0] = 3.0  # one constant dimension
        preprocessor = EmbeddingPreprocessor.fit(train, n_components=3)
        assert preprocessor.scales[0] == pytest.approx(1.0)
        assert np.all(np.isfinite(preprocessor.transform(train)))


class TestPcaDimensionSelectionNeverTouchesValidation:
    def test_signature_only_accepts_development_arguments(self):
        import inspect

        params = list(inspect.signature(select_pca_dimension).parameters)
        assert params == ["dev_rows_by_tone", "dev_embeddings_by_tone"]

    def test_never_references_a_validation_identifier(self):
        """Bytecode names/vars, not source text -- the function's own
        docstring explains the guarantee using the word "validation", which
        would make a plain text search trip on the documentation itself
        rather than on real data access."""
        code = select_pca_dimension.__code__
        suspicious = {"val_rows_by_tone", "val_embeddings_by_tone", "validation", "val_rows", "val_matrix"}
        assert not (suspicious & set(code.co_names))
        assert not (suspicious & set(code.co_varnames))


class TestGroupedCvNeverLeaksASpeaker:
    def _dev_data(self, toy_corpus):
        _split, split_path, csv_path = toy_corpus
        rows = load_split_rows("development", diagnostics_csv=csv_path, split_path=split_path)
        rng = np.random.default_rng(6)
        matrix = rng.normal(size=(len(rows), EMBEDDING_DIM)).astype(np.float32)
        return _group_rows_and_embeddings_by_tone(rows, matrix)

    def test_no_row_in_a_held_out_fold_shares_a_speaker_with_that_folds_training_rows(self, toy_corpus):
        by_tone_rows, by_tone_matrix = self._dev_data(toy_corpus)
        cv = run_grouped_cv(by_tone_rows, by_tone_matrix, pca_dim=5, k=3)
        for train_speakers, held_out_speakers in cv["folds"]:
            assert not (set(train_speakers) & set(held_out_speakers))

    def test_out_of_fold_probabilities_are_valid(self, toy_corpus):
        by_tone_rows, by_tone_matrix = self._dev_data(toy_corpus)
        cv = run_grouped_cv(by_tone_rows, by_tone_matrix, pca_dim=5, k=3)
        for tone in ("1", "2", "3", "4"):
            oof = cv["oof"][tone]["probabilities"]
            scored = oof[~np.isnan(oof)]
            assert np.all((scored >= 0) & (scored <= 1))


class TestBuildEmbeddingsCache:
    def test_caches_and_reuses_without_calling_the_encoder_again(self, toy_corpus, tmp_path):
        _split, split_path, csv_path = toy_corpus
        rows = load_split_rows("development", diagnostics_csv=csv_path, split_path=split_path)[:10]

        with patch("benchmarking.candidates.wav2vec_frozen_logistic.CACHE_DIR", tmp_path / "cache"):
            encoder = FakeEncoder()
            matrix1, valid1, missing1, _ = build_embeddings(rows, "development", encoder=encoder)
            first_call_count = encoder.calls
            assert first_call_count == len(rows)
            assert missing1 == 0
            assert valid1.all()

            # Second call: cache should short-circuit every row, so the
            # encoder is never invoked again even though we don't pass one.
            matrix2, valid2, missing2, encoder2 = build_embeddings(rows, "development", encoder=None)
            assert encoder2 is None  # never had to be constructed
            assert np.allclose(matrix1, matrix2)

    def test_rows_with_no_span_are_excluded_not_imputed(self, toy_corpus, tmp_path):
        _split, split_path, csv_path = toy_corpus
        rows = load_split_rows("development", diagnostics_csv=csv_path, split_path=split_path)[:5]
        rows = [dict(r) for r in rows]
        rows[0]["syllable_start_time"] = "NA"
        rows[0]["syllable_end_time"] = "NA"

        with patch("benchmarking.candidates.wav2vec_frozen_logistic.CACHE_DIR", tmp_path / "cache"):
            matrix, valid, missing, _ = build_embeddings(rows, "development", encoder=FakeEncoder())
        assert missing == 1
        assert valid[0] == False  # noqa: E712 -- explicit bool check reads clearer here
        assert valid[1:].all()

    def test_metadata_file_records_checkpoint_and_frozen_flag(self, toy_corpus, tmp_path):
        _split, split_path, csv_path = toy_corpus
        rows = load_split_rows("development", diagnostics_csv=csv_path, split_path=split_path)[:3]
        cache_dir = tmp_path / "cache"
        with patch("benchmarking.candidates.wav2vec_frozen_logistic.CACHE_DIR", cache_dir):
            build_embeddings(rows, "development", encoder=FakeEncoder())
        import json

        meta = json.loads((cache_dir / "development_embeddings_meta.json").read_text(encoding="utf-8"))
        assert meta["encoder_frozen"] is True
        assert meta["pooling"] == "mean"
        assert meta["checkpoint"] == "fake/test-checkpoint"
        for key in [_row_key(r) for r in rows]:
            entry = meta["rows"][key]
            assert entry["speaker_id"]
            assert entry["expected_tone"] in ("1", "2", "3", "4")
            assert entry["split"] == "development"


@pytest.fixture(scope="module")
def real_encoder():
    from benchmarking.candidates.wav2vec_frozen_logistic import FrozenEncoder

    return FrozenEncoder()


class TestRealEncoder:
    """Touches the actual checkpoint — kept to a minimum, one shared fixture."""

    def test_checkpoint_identity_matches_the_audited_checkpoint(self, real_encoder):
        assert real_encoder.checkpoint in (
            CHECKPOINT_NAME,
            "facebook/wav2vec2-base",  # FrozenWav2Vec2's own documented fallback
        )

    def test_encoder_parameters_remain_frozen_after_use(self, real_encoder):
        for parameter in real_encoder._impl.model.parameters():
            assert parameter.requires_grad is False
        assert real_encoder._impl.trainable_parameters == 0

    def test_embedding_generation_is_deterministic(self, real_encoder, tmp_path):
        import soundfile as sf

        rng = np.random.default_rng(7)
        audio = rng.normal(scale=0.05, size=16000).astype(np.float32)  # 1s of noise
        path = tmp_path / "sample.wav"
        sf.write(str(path), audio, 16000)

        first = real_encoder.embed_span(str(path), 0.1, 0.5)
        second = real_encoder.embed_span(str(path), 0.1, 0.5)
        assert first is not None
        np.testing.assert_array_equal(first, second)

    def test_span_shorter_than_minimum_returns_none(self, real_encoder, tmp_path):
        import soundfile as sf

        audio = np.zeros(16000, dtype=np.float32)
        path = tmp_path / "sample.wav"
        sf.write(str(path), audio, 16000)

        assert real_encoder.embed_span(str(path), 0.0, 0.001) is None
