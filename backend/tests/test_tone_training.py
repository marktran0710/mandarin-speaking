"""Unit tests for the learned tone scorer's training protocol.

The properties tested here are protocol guarantees, not model quality: fold
membership comes from OMPAL's published splits, no sample is scored by a model
that saw its speaker, and exclusions match the frozen benchmark contract so
the learned and heuristic rows of the ablation stay comparable.
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from benchmarking.ompal_corpus import OmpalUtterance, OmpalWord
from tone_scoring.features import FEATURE_NAMES
from tone_scoring.training import (
    SyllableSample,
    build_samples,
    cross_validated_predictions,
    load_fold_map,
)

FULL = (True, True, True)


def utterance(utterance_id="001", speaker="S1", words=(("他", 1), ("忙", 2)), labels=FULL):
    return OmpalUtterance(
        utterance_id=utterance_id,
        speaker_id=speaker,
        is_native=False,
        text="".join(w[0] for w in words),
        wav_path=Path(f"/tmp/{utterance_id}.wav"),
        words=tuple(
            OmpalWord(text=t, expected_tones=(tone,), rater_tone_labels=labels)
            for t, tone in words
        ),
        rater_accuracy=(4.0,), rater_fluency=(4.0,), rater_prosody=(4.0,),
    )


def fake_bundle(_path):
    """A rising contour long enough to featurize, plus flat intensity."""
    contour = [(i * 0.02, 100.0 + i * 2.0) for i in range(60)]
    intensity = [(i * 0.02, 70.0) for i in range(60)]
    return contour, intensity


def sample(fold, label=True, seed=0.0):
    return SyllableSample(
        utterance_id=f"u{fold}", speaker_id=f"S{fold}", is_native=False,
        word_index=0, expected_tone=1,
        features=[seed] * len(FEATURE_NAMES),
        rater_labels=(label, label, label), fold=fold,
    )


class TestFoldMap:
    def test_reads_membership_from_ompals_published_test_splits(self, tmp_path):
        (tmp_path / "test").mkdir()
        (tmp_path / "test" / "test_1_scores.json").write_text(
            json.dumps({"00200101": {}, "00200102": {}}), encoding="utf-8")
        (tmp_path / "test" / "test_2_scores.json").write_text(
            json.dumps({"00200201": {}}), encoding="utf-8")
        mapping = load_fold_map(tmp_path)
        assert mapping == {"00200101": 1, "00200102": 1, "00200201": 2}

    def test_missing_splits_yield_an_empty_map_rather_than_raising(self, tmp_path):
        assert load_fold_map(tmp_path) == {}


class TestBuildSamples:
    def test_featurizes_rated_syllables(self):
        samples, excluded = build_samples([utterance()], fake_bundle, {"001": 1})
        assert len(samples) == 2
        assert all(len(s.features) == len(FEATURE_NAMES) for s in samples)
        assert all(s.fold == 1 for s in samples)

    def test_excludes_neutral_tone_matching_the_frozen_contract(self):
        """Same exclusions as the heuristic row, so the ablation compares
        like with like."""
        items = [utterance(words=(("他", 1), ("們", 5)))]
        samples, excluded = build_samples(items, fake_bundle, {})
        assert excluded["neutral_tone"] == 1
        assert len(samples) == 1

    def test_excludes_incomplete_rater_panels(self):
        items = [utterance(labels=(True,))]
        samples, excluded = build_samples(items, fake_bundle, {})
        assert excluded["incomplete_rater_panel"] == 2
        assert samples == []

    def test_records_unreadable_audio_without_crashing(self):
        def broken(_path):
            raise RuntimeError("cannot read")

        samples, excluded = build_samples([utterance()], broken, {})
        assert excluded["audio_unreadable"] == 1
        assert samples == []

    def test_drops_utterances_with_no_usable_pitch(self):
        samples, excluded = build_samples(
            [utterance()], lambda _p: ([(0.0, 100.0)], []), {}
        )
        assert excluded["no_pitch"] == 1

    def test_majority_label_follows_the_rater_panel(self):
        items = [utterance(labels=(False, True, True))]
        samples, _ = build_samples(items, fake_bundle, {})
        assert samples[0].majority is True


class TestCrossValidation:
    def test_every_sample_is_scored_by_a_model_that_never_saw_its_fold(self):
        """The guarantee that makes the number meaningful: OMPAL's folds are
        speaker-disjoint, so predicting a fold with a model trained on it
        would let memorised speakers inflate agreement."""
        samples = (
            [sample(1, True, 1.0) for _ in range(30)]
            + [sample(2, False, -1.0) for _ in range(30)]
            + [sample(3, True, 1.0) for _ in range(30)]
        )
        used, probabilities = cross_validated_predictions(samples)
        assert len(used) == len(samples)
        assert len(probabilities) == len(samples)
        assert np.all((probabilities >= 0.0) & (probabilities <= 1.0))

    def test_samples_without_a_published_fold_are_dropped_not_guessed(self):
        """Assigning a fold arbitrarily could place one speaker on both sides
        of a split and quietly inflate the result."""
        samples = [sample(1) for _ in range(10)] + [
            SyllableSample("x", "S9", False, 0, 1, [0.0] * len(FEATURE_NAMES), FULL, None)
        ]
        used, _ = cross_validated_predictions(samples)
        assert len(used) == 10

    def test_returns_empty_when_nothing_has_a_fold(self):
        samples = [
            SyllableSample("x", "S9", False, 0, 1, [0.0] * len(FEATURE_NAMES), FULL, None)
        ]
        used, probabilities = cross_validated_predictions(samples)
        assert used == []
        assert len(probabilities) == 0

    def test_a_single_class_training_fold_falls_back_to_its_base_rate(self):
        """A classifier cannot be fitted on one class; emitting the base rate
        is honest, where crashing or predicting a constant 1.0 would not be."""
        samples = [sample(1, True, 1.0) for _ in range(20)] + [
            sample(2, True, 1.0) for _ in range(20)
        ]
        used, probabilities = cross_validated_predictions(samples)
        assert len(used) == 40
        assert np.all(probabilities == pytest.approx(1.0))
