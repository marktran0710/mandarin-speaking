"""Tests for the experimental wav2vec2 tone module.

These cover the parts whose failure would be silent: a speaker leaking across
the split, audio reaching the encoder at the wrong rate, or a prediction whose
probabilities are mislabelled. Encoder behaviour itself is exercised by
smoke_test.py, which needs the model weights.
"""
import csv
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pronunciation.wav2vec_tone.dataset import (
    load_dataset,
    speaker_independent_split,
    tone_distribution,
)
from pronunciation.wav2vec_tone.extract_embeddings import (
    TARGET_SAMPLE_RATE,
    load_audio_16k_mono,
)
from pronunciation.wav2vec_tone.prepare_dataset import classify, parse_syllable
from pronunciation.wav2vec_tone.train_classifier import (
    assert_no_speaker_overlap,
    build_classifier,
    speaker_split_mask,
)


def write_csv(tmp_path, rows, header=("audio_path", "speaker_id", "pinyin", "tone")):
    path = tmp_path / "tones.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    return path


class TestSyllableParsing:
    """Filtering decides what the classifier ever sees, so a wrong verdict here
    is invisible downstream -- the dataset simply looks smaller or cleaner than
    it is."""

    @pytest.mark.parametrize("pinyin,expected", [
        ("ma1", ("ma", 1)), ("shi4", ("shi", 4)), ("hao3", ("hao", 3)),
    ])
    def test_keeps_single_syllables(self, pinyin, expected):
        assert parse_syllable(pinyin) == expected

    @pytest.mark.parametrize("pinyin", ["ke1 xue2", "fa1 zhan3", "wo3 men5"])
    def test_rejects_multi_syllables(self, pinyin):
        assert classify(pinyin)[0] == "multi_syllable"

    def test_neutral_tone_is_excluded_separately_from_invalid(self):
        """Two different reasons, reported as two different numbers."""
        assert classify("ma5")[0] == "neutral_tone"
        assert classify("xyz")[0] == "invalid"
        assert classify("")[0] == "invalid"

    def test_lu_and_lv_stay_distinct(self):
        """`v` spells ü, not u: 綠 lv4 and 路 lu4 are different syllables.

        Folding v onto u would merge them, understating the syllable count and
        letting a syllable-overlap check believe two syllables are one.
        """
        assert parse_syllable("lv4")[0] == "lv"
        assert parse_syllable("lu4")[0] == "lu"
        assert parse_syllable("nv3")[0] != parse_syllable("nu3")[0]

    def test_all_three_umlaut_spellings_agree(self):
        assert parse_syllable("lv4")[0] == parse_syllable("lu:4")[0] == "lv"
        assert parse_syllable("lü4")[0] == "lv"


class TestDatasetLoading:
    def test_reads_the_documented_csv_format(self, tmp_path):
        path = write_csv(tmp_path, [
            ("audio/001.wav", "S001", "ma1", 1),
            ("audio/002.wav", "S002", "ma2", 2),
        ])
        samples = load_dataset(path)
        assert [s.tone for s in samples] == [1, 2]
        assert samples[0].pinyin == "ma1"

    def test_resolves_audio_paths_relative_to_the_csv(self, tmp_path):
        path = write_csv(tmp_path, [("audio/001.wav", "S1", "ma1", 1)])
        assert load_dataset(path)[0].audio_path == tmp_path / "audio" / "001.wav"

    def test_rejects_a_missing_column_by_name(self, tmp_path):
        path = write_csv(
            tmp_path, [("audio/001.wav", "S1", 1)],
            header=("audio_path", "speaker_id", "tone"),
        )
        with pytest.raises(ValueError, match="pinyin"):
            load_dataset(path)

    def test_reports_the_line_number_of_a_bad_row(self, tmp_path):
        """Skipping malformed rows silently would change the class balance and
        nobody would notice."""
        path = write_csv(tmp_path, [
            ("audio/001.wav", "S1", "ma1", 1),
            ("audio/002.wav", "S2", "ma5", 5),      # neutral tone is out of scope
        ])
        with pytest.raises(ValueError, match="line 3"):
            load_dataset(path)

    def test_rejects_a_blank_speaker_id(self, tmp_path):
        path = write_csv(tmp_path, [("audio/001.wav", "", "ma1", 1)])
        with pytest.raises(ValueError, match="cannot be blank"):
            load_dataset(path)

    def test_counts_tones(self, tmp_path):
        path = write_csv(tmp_path, [
            ("a.wav", "S1", "ma1", 1), ("b.wav", "S1", "ma1", 1),
            ("c.wav", "S2", "ma4", 4),
        ])
        assert tone_distribution(load_dataset(path)) == {1: 2, 2: 0, 3: 0, 4: 1}


class TestSpeakerIndependence:
    """The evaluation rests entirely on this. A classifier that heard a speaker
    in training can recognise that voice rather than the tone, which does not
    degrade the reported accuracy -- it invalidates it while still looking good.
    """

    def test_no_speaker_appears_on_both_sides(self, tmp_path):
        path = write_csv(tmp_path, [
            (f"{i}.wav", f"S{i % 6}", "ma1", (i % 4) + 1) for i in range(60)
        ])
        train, test = speaker_independent_split(load_dataset(path))
        assert not ({s.speaker_id for s in train} & {s.speaker_id for s in test})

    def test_both_sides_are_non_empty(self, tmp_path):
        path = write_csv(tmp_path, [
            (f"{i}.wav", f"S{i % 4}", "ma1", 1) for i in range(20)
        ])
        train, test = speaker_independent_split(load_dataset(path))
        assert train and test

    def test_a_single_speaker_dataset_raises(self, tmp_path):
        """Better than returning a split that only looks valid."""
        path = write_csv(tmp_path, [(f"{i}.wav", "S1", "ma1", 1) for i in range(10)])
        with pytest.raises(ValueError, match="at least 2 speakers"):
            speaker_independent_split(load_dataset(path))

    def test_the_split_is_reproducible(self, tmp_path):
        path = write_csv(tmp_path, [
            (f"{i}.wav", f"S{i % 8}", "ma1", 1) for i in range(40)
        ])
        samples = load_dataset(path)
        first = speaker_independent_split(samples, seed=7)[1]
        second = speaker_independent_split(samples, seed=7)[1]
        assert [s.audio_path for s in first] == [s.audio_path for s in second]

    def test_the_mask_helper_agrees_with_the_dataset_helper(self):
        speakers = np.asarray([f"S{i % 6}" for i in range(60)], dtype=object)
        mask, held_out = speaker_split_mask(speakers, 0.25, 0)
        assert set(str(s) for s in speakers[mask]) == set(held_out)

    def test_the_overlap_assertion_fires_on_a_leak(self):
        with pytest.raises(AssertionError, match="SPEAKER LEAK"):
            assert_no_speaker_overlap(["S1", "S2"], ["S2", "S3"])

    def test_the_overlap_assertion_passes_when_disjoint(self):
        assert assert_no_speaker_overlap(["S1", "S2"], ["S3"]) == 0


class TestAudioPreprocessing:
    def test_converts_stereo_to_mono(self, tmp_path):
        import soundfile as sf

        path = tmp_path / "stereo.wav"
        sf.write(path, np.zeros((TARGET_SAMPLE_RATE, 2), dtype="float32"), TARGET_SAMPLE_RATE)
        assert load_audio_16k_mono(path).ndim == 1

    def test_resamples_to_16k(self, tmp_path):
        """wav2vec2 was trained at 16 kHz; another rate silently changes the
        effective speed of the audio and every frame the model produces."""
        import soundfile as sf

        path = tmp_path / "highrate.wav"
        sf.write(path, np.zeros(44100, dtype="float32"), 44100)   # 1.0 second
        audio = load_audio_16k_mono(path)
        assert len(audio) == pytest.approx(TARGET_SAMPLE_RATE, rel=0.01)

    def test_leaves_16k_mono_untouched(self, tmp_path):
        import soundfile as sf

        path = tmp_path / "ok.wav"
        original = np.linspace(-0.5, 0.5, TARGET_SAMPLE_RATE, dtype="float32")
        sf.write(path, original, TARGET_SAMPLE_RATE)
        assert len(load_audio_16k_mono(path)) == TARGET_SAMPLE_RATE


class TestClassifier:
    def test_probabilities_are_labelled_by_the_fitted_class_order(self):
        """predict.py reads classes off the model rather than assuming
        1,2,3,4; a mismatch would silently relabel every prediction."""
        rng = np.random.default_rng(0)
        features = np.vstack([
            rng.normal(tone, 0.2, size=(25, 6)) for tone in (1, 2, 3, 4)
        ])
        labels = np.repeat([1, 2, 3, 4], 25)
        model = build_classifier().fit(features, labels)
        assert list(model.classes_) == [1, 2, 3, 4]
        probabilities = model.predict_proba(features[:1])[0]
        assert probabilities.sum() == pytest.approx(1.0)
        assert len(probabilities) == 4

    def test_uses_balanced_class_weight(self):
        model = build_classifier()
        assert model[-1].class_weight == "balanced"

    def test_is_reproducible_for_a_fixed_seed(self):
        rng = np.random.default_rng(1)
        features = rng.normal(size=(80, 6))
        labels = np.tile([1, 2, 3, 4], 20)
        first = build_classifier(seed=3).fit(features, labels).predict(features)
        second = build_classifier(seed=3).fit(features, labels).predict(features)
        assert np.array_equal(first, second)
