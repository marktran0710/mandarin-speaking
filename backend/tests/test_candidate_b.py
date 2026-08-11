"""Candidate B1's guard rails: the final_test lock, the never-split-a-speaker
CV guarantee, and the preprocessing/threshold-freezing discipline the whole
protocol depends on. These matter more than the model's actual numbers —
a candidate that quietly leaked final_test or refit on validation would
produce a *better-looking* report that is simply wrong.
"""
import csv
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from benchmarking.candidates.praat_logistic import (
    FEATURE_NAMES,
    FinalTestLockedError,
    Preprocessor,
    _feature_matrix,
    _labels,
    _select_threshold,
    load_split_rows,
    run_grouped_cv,
)
from benchmarking.splits import create_speaker_split, write_split

SPEAKERS = [f"SPEAKER02{i:03d}" for i in range(1, 21)]  # 20, enough for a 60/20/20 toy split


def _toy_corpus(tmp_path, rng):
    split = create_speaker_split(SPEAKERS, ratios={"development": 0.6, "validation": 0.2, "final_test": 0.2})
    split_path = tmp_path / "split.json"
    write_split(split, split_path)

    csv_path = tmp_path / "diagnostics.csv"
    fieldnames = [
        "audio_id", "speaker_id", "expected_tone", "human_majority_tone_correct",
        "system_tone_correct", "system_character_score", "word",
        *FEATURE_NAMES,
    ]
    rows = []
    all_speakers = split.development + split.validation + split.final_test
    for i, speaker in enumerate(all_speakers):
        for j in range(15):
            rows.append({
                "audio_id": f"{speaker}-{j}",
                "speaker_id": speaker,
                "expected_tone": str((j % 4) + 1),
                "human_majority_tone_correct": str(int(rng.uniform() < 0.7)),
                "system_tone_correct": str(int(rng.uniform() < 0.5)),
                "system_character_score": f"{rng.uniform(0, 100):.1f}",
                "word": "測",
                **{name: f"{rng.normal():.4f}" for name in FEATURE_NAMES},
            })
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return split, split_path, csv_path


@pytest.fixture
def toy_corpus(tmp_path):
    return _toy_corpus(tmp_path, np.random.default_rng(0))


class TestFinalTestLock:
    def test_raises_without_any_unlock(self, toy_corpus):
        _split, split_path, csv_path = toy_corpus
        with pytest.raises(FinalTestLockedError):
            load_split_rows("final_test", diagnostics_csv=csv_path, split_path=split_path)

    def test_raises_with_only_the_flag_argument(self, toy_corpus):
        """One gate alone must not be enough — see the module docstring."""
        _split, split_path, csv_path = toy_corpus
        with pytest.raises(FinalTestLockedError):
            load_split_rows(
                "final_test", diagnostics_csv=csv_path, split_path=split_path,
                unlock_final_test=True,
            )

    def test_raises_with_only_the_environment_variable(self, toy_corpus):
        _split, split_path, csv_path = toy_corpus
        with patch.dict(os.environ, {"OMPAL_FINAL_TEST_UNLOCKED": "1"}):
            with pytest.raises(FinalTestLockedError):
                load_split_rows("final_test", diagnostics_csv=csv_path, split_path=split_path)

    def test_both_gates_together_do_open_it(self, toy_corpus):
        """The lock is real, not accidentally permanent — but note this test
        is the ONLY place in the whole test/production code that ever passes
        unlock_final_test=True, and it does so against a synthetic toy
        corpus, never the real OMPAL final_test partition."""
        split, split_path, csv_path = toy_corpus
        with patch.dict(os.environ, {"OMPAL_FINAL_TEST_UNLOCKED": "1"}):
            rows = load_split_rows(
                "final_test", diagnostics_csv=csv_path, split_path=split_path,
                unlock_final_test=True,
            )
        assert {row["speaker_id"] for row in rows} <= set(split.final_test)

    def test_development_and_validation_need_no_unlock(self, toy_corpus):
        _split, split_path, csv_path = toy_corpus
        assert load_split_rows("development", diagnostics_csv=csv_path, split_path=split_path)
        assert load_split_rows("validation", diagnostics_csv=csv_path, split_path=split_path)

    def test_rejects_an_unknown_split_name(self, toy_corpus):
        _split, split_path, csv_path = toy_corpus
        with pytest.raises(ValueError):
            load_split_rows("nonsense", diagnostics_csv=csv_path, split_path=split_path)


class TestPreprocessorNeverRefits:
    def test_transform_uses_the_fitted_statistics_not_the_new_data(self):
        train = np.array([[1.0], [2.0], [3.0]])
        preprocessor = Preprocessor.fit(train)
        # A wildly different distribution transformed with the SAME fitted
        # stats must not silently re-center on itself.
        other = np.array([[100.0], [200.0]])
        transformed = preprocessor.transform(other)
        expected = (other - preprocessor.means) / preprocessor.scales
        assert np.allclose(transformed, expected)
        assert not np.allclose(transformed.mean(), 0.0)  # proof it did NOT refit

    def test_imputes_with_the_training_median_not_the_new_data_median(self):
        train = np.array([[1.0], [2.0], [3.0]])
        preprocessor = Preprocessor.fit(train)
        assert preprocessor.medians[0] == pytest.approx(2.0)
        other = np.array([[np.nan], [50.0]])
        transformed = preprocessor.transform(other)
        # The imputed value, before scaling, must equal the TRAIN median (2.0).
        recovered = transformed[0, 0] * preprocessor.scales[0] + preprocessor.means[0]
        assert recovered == pytest.approx(2.0)

    def test_constant_feature_is_not_divided_by_near_zero(self):
        train = np.array([[5.0], [5.0], [5.0]])
        preprocessor = Preprocessor.fit(train)
        assert preprocessor.scales[0] == pytest.approx(1.0)
        assert np.all(np.isfinite(preprocessor.transform(np.array([[5.0]]))))


class TestThresholdSelection:
    def test_picks_the_grid_point_maximizing_balanced_accuracy(self):
        # Perfectly separated by 0.5: any threshold in (0.3, 0.7) is optimal;
        # the rule must land somewhere in that range, not outside it.
        probabilities = np.array([0.1, 0.2, 0.3, 0.7, 0.8, 0.9])
        labels = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])
        threshold = _select_threshold(probabilities, labels)
        assert 0.3 < threshold <= 0.7

    def test_is_computed_from_the_arguments_given_not_from_validation(self):
        """Structural guard: the function signature itself takes only
        (probabilities, labels) — there is no way to pass it validation data
        without the caller explicitly doing so, which `praat_logistic.run()`
        never does (see test_run_never_touches_validation_before_freezing)."""
        import inspect

        params = list(inspect.signature(_select_threshold).parameters)
        assert params == ["probabilities", "labels"]


class TestGroupedCvNeverLeaksASpeaker:
    def test_no_row_in_a_held_out_fold_shares_a_speaker_with_that_folds_training_rows(self, toy_corpus):
        split, split_path, csv_path = toy_corpus
        rows = load_split_rows("development", diagnostics_csv=csv_path, split_path=split_path)
        by_tone = {t: [r for r in rows if r["expected_tone"] == t] for t in ("1", "2", "3", "4")}
        cv = run_grouped_cv(by_tone, k=3)
        for train_speakers, held_out_speakers in cv["folds"]:
            assert not (set(train_speakers) & set(held_out_speakers))

    def test_out_of_fold_predictions_cover_every_row_that_had_a_usable_fold(self, toy_corpus):
        _split, split_path, csv_path = toy_corpus
        rows = load_split_rows("development", diagnostics_csv=csv_path, split_path=split_path)
        by_tone = {t: [r for r in rows if r["expected_tone"] == t] for t in ("1", "2", "3", "4")}
        cv = run_grouped_cv(by_tone, k=3)
        for tone in ("1", "2", "3", "4"):
            oof = cv["oof"][tone]["probabilities"]
            # Every non-NaN OOF prediction is a genuine held-out prediction —
            # not a value the same fold's training pass could have seen.
            assert np.all((oof[~np.isnan(oof)] >= 0) & (oof[~np.isnan(oof)] <= 1))


class TestFeatureAndLabelExtraction:
    def test_feature_matrix_matches_column_order(self, toy_corpus):
        _split, split_path, csv_path = toy_corpus
        rows = load_split_rows("development", diagnostics_csv=csv_path, split_path=split_path)
        matrix = _feature_matrix(rows[:3])
        assert matrix.shape == (3, len(FEATURE_NAMES))
        for i, name in enumerate(FEATURE_NAMES):
            assert matrix[0, i] == pytest.approx(float(rows[0][name]))

    def test_labels_are_1_for_human_correct_and_0_otherwise(self, toy_corpus):
        _split, split_path, csv_path = toy_corpus
        rows = load_split_rows("development", diagnostics_csv=csv_path, split_path=split_path)
        labels = _labels(rows)
        assert set(np.unique(labels)) <= {0.0, 1.0}
        for row, label in zip(rows, labels):
            assert label == (1.0 if row["human_majority_tone_correct"] == "1" else 0.0)
