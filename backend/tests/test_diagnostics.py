"""Per-syllable diagnostic extraction, and the identity check it stands on.

The identity check is the load-bearing part of this module: everything else
it reports is only trustworthy if the re-computed score is provably the same
score already cached. These tests cover both halves — that a genuine
mismatch is caught (`FrozenScoreMismatchError`), and that the analysis
functions built on top of a row summarise it correctly.
"""
import os
import sys
import wave
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from benchmarking.diagnostics import (
    CONFUSION_FN,
    CONFUSION_FP,
    CONFUSION_TN,
    CONFUSION_TP,
    FrozenScoreMismatchError,
    _confusion_group,
    _f0_features,
    _slope,
    _syllable_spans,
    duration_bins,
    extract_utterance_rows,
    group_comparison,
    per_tone_diagnostics,
    position_effect,
    score_discrimination,
    unanimous_subset,
    voicing_effect,
)
from benchmarking.error_analysis import NA
from benchmarking.ompal_corpus import OmpalUtterance, OmpalWord
from benchmarking.ompal_runner import flatten_characters
from praat_analyzer import analyze_all


# ── Pure helpers: no audio needed ──────────────────────────────────────────


class TestConfusionGroup:
    @pytest.mark.parametrize(
        "human,system,expected",
        [
            (True, True, CONFUSION_TP),
            (False, False, CONFUSION_TN),
            (False, True, CONFUSION_FP),
            (True, False, CONFUSION_FN),
        ],
    )
    def test_all_four_combinations(self, human, system, expected):
        assert _confusion_group(human, system) == expected


class TestF0Features:
    def test_slope_is_hz_per_second(self):
        # +100 Hz over 0.5s -> 200 Hz/s.
        assert _slope([(0.0, 200.0), (0.5, 300.0)]) == pytest.approx(200.0)

    def test_slope_is_none_for_a_single_point(self):
        assert _slope([(0.0, 200.0)]) is None

    def test_features_read_off_a_synthetic_rising_contour(self):
        frames = [(i * 0.01, 200.0 + i * 5) for i in range(20)]  # 200 -> 295 Hz
        features = _f0_features(frames)
        assert features["f0_min"] == pytest.approx(200.0)
        assert features["f0_max"] == pytest.approx(295.0)
        assert features["f0_start"] == pytest.approx(200.0)
        assert features["f0_end"] == pytest.approx(295.0)
        assert features["f0_slope_full"] > 0
        assert features["normalized_f0_end"] > features["normalized_f0_start"]

    def test_too_few_frames_is_na_not_zero(self):
        """A single voiced frame says nothing about a shape. NA, not a
        fabricated flat reading."""
        features = _f0_features([(0.0, 200.0)])
        assert features["f0_mean"] == NA
        assert features["f0_slope_full"] == NA


class TestSyllableSpans:
    def test_recovers_one_span_per_syllable(self):
        contour = [(i * 0.01, 200.0 + 10 * (i % 5)) for i in range(120)]
        spans = _syllable_spans(contour, "你好嗎", intensity=None)
        assert spans is not None
        assert len(spans) == 3
        # Spans should be contiguous and increasing.
        assert spans[0][0] < spans[0][1] <= spans[1][0]

    def test_none_for_a_degenerate_contour(self):
        assert _syllable_spans([], "你好", intensity=None) is None
        assert _syllable_spans([(0.0, 200.0)], "你好", intensity=None) is None


# ── Analysis functions: hand-built rows, no audio ──────────────────────────


def _row(**overrides):
    base = {
        "confusion_group": CONFUSION_TP,
        "expected_tone": 1,
        "duration_seconds": 0.15,
        "voiced_fraction": 0.8,
        "utterance_position_normalized": 0.5,
        "syllable_index": 0,
        "system_character_score": 80.0,
        "human_majority_tone_correct": 1,
        "individual_rater_labels": "111",
    }
    base.update(overrides)
    return base


class TestGroupComparison:
    def test_splits_a_feature_by_confusion_group(self):
        rows = [
            _row(confusion_group=CONFUSION_TP, duration_seconds=0.20),
            _row(confusion_group=CONFUSION_FN, duration_seconds=0.05),
            _row(confusion_group=CONFUSION_FN, duration_seconds=0.06),
        ]
        result = group_comparison(rows, "duration_seconds")
        assert result[CONFUSION_TP]["n"] == 1
        assert result[CONFUSION_FN]["n"] == 2
        assert result[CONFUSION_FN]["median"] == pytest.approx(0.055)
        assert result[CONFUSION_TN]["n"] == 0

    def test_na_values_are_excluded_not_zeroed(self):
        rows = [_row(duration_seconds=NA), _row(duration_seconds=0.1)]
        result = group_comparison(rows, "duration_seconds")
        assert result[CONFUSION_TP]["n"] == 1


class TestPerToneDiagnostics:
    def test_computes_false_rejection_rate_per_tone(self):
        rows = [
            _row(expected_tone=2, confusion_group=CONFUSION_FN),
            _row(expected_tone=2, confusion_group=CONFUSION_TP),
            _row(expected_tone=2, confusion_group=CONFUSION_TP),
            _row(expected_tone=1, confusion_group=CONFUSION_TP),
        ]
        result = per_tone_diagnostics(rows, "duration_seconds")
        assert result["2"]["n"] == 3
        assert result["2"]["false_rejection_rate"] == pytest.approx(1 / 3)
        assert result["1"]["false_rejection_rate"] == pytest.approx(0.0)
        assert result["3"]["n"] == 0


class TestDurationBins:
    def test_bins_by_edges_and_reports_accuracy(self):
        rows = [
            _row(duration_seconds=0.05, confusion_group=CONFUSION_FN),  # short, rejected
            _row(duration_seconds=0.25, confusion_group=CONFUSION_TP),  # long, correct
        ]
        result = duration_bins(rows, edges=[0.0, 0.1, 0.2])
        assert result["0.00-0.10s"]["n"] == 1
        assert result["0.00-0.10s"]["accuracy"] == pytest.approx(0.0)
        assert result[">0.20s"]["n"] == 1
        assert result[">0.20s"]["accuracy"] == pytest.approx(1.0)


class TestPositionEffect:
    def test_buckets_by_normalized_position(self):
        rows = [
            _row(utterance_position_normalized=0.05, confusion_group=CONFUSION_FN),
            _row(utterance_position_normalized=0.95, confusion_group=CONFUSION_TP),
        ]
        result = position_effect(rows, bins=5)
        buckets = result["by_normalized_position"]
        assert buckets["0.0-0.2"]["n"] == 1
        assert buckets["0.8-1.0"]["n"] == 1


class TestVoicingEffect:
    def test_splits_into_terciles_by_voiced_fraction(self):
        rows = [_row(voiced_fraction=v, confusion_group=CONFUSION_TP) for v in (0.1, 0.5, 0.9)]
        result = voicing_effect(rows)
        assert result["low_voicing (bottom third)"]["n"] == 1

    def test_empty_input_is_handled(self):
        assert "note" in voicing_effect([])


class TestScoreDiscrimination:
    def test_auc_reflects_separation(self):
        rows = [
            _row(system_character_score=10, human_majority_tone_correct=0),
            _row(system_character_score=90, human_majority_tone_correct=1),
        ]
        result = score_discrimination(rows)
        assert result["overall"]["auc"] == pytest.approx(1.0)


class TestUnanimousSubset:
    def test_keeps_only_000_and_111_panels(self):
        rows = [
            _row(individual_rater_labels="111", confusion_group=CONFUSION_TP),
            _row(individual_rater_labels="110", confusion_group=CONFUSION_TP),
            _row(individual_rater_labels="000", confusion_group=CONFUSION_TN),
        ]
        subset, summary = unanimous_subset(rows)
        assert len(subset) == 2
        assert summary["n"] == 2
        assert summary["accuracy"] == pytest.approx(1.0)


# ── End-to-end extraction against a real (synthetic) WAV ──────────────────


@pytest.fixture
def synthetic_utterance(tmp_path):
    """One two-character utterance, real enough for Parselmouth to track
    pitch on, so `extract_utterance_rows` runs its full real path."""
    import math
    import struct

    sample_rate = 16000
    duration = 0.8
    n = int(duration * sample_rate)
    # A gently falling tone, loud enough to clear the pitch floor.
    samples = [
        int(20000 * math.sin(2 * math.pi * (220 - 60 * i / n) * i / sample_rate))
        for i in range(n)
    ]
    path = tmp_path / "utt.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(struct.pack(f"<{n}h", *samples))

    utterance = OmpalUtterance(
        utterance_id="00299901",
        speaker_id="SPEAKER02999",
        is_native=False,
        text="他好",
        wav_path=path,
        words=(
            OmpalWord(text="他", expected_tones=(1,), rater_tone_labels=(True, True, True)),
            OmpalWord(text="好", expected_tones=(3,), rater_tone_labels=(False, False, True)),
        ),
        rater_accuracy=(4.0,), rater_fluency=(4.0,), rater_prosody=(4.0,),
    )
    return utterance


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("parselmouth") is None,
    reason="Parselmouth not installed",
)
class TestExtractUtteranceRows:
    def _cached_row(self, utterance, threshold):
        result = analyze_all(str(utterance.wav_path), utterance.text)
        return {
            "utterance_id": utterance.utterance_id,
            "characters": flatten_characters(result[5]),
            "error": None,
        }

    def test_produces_one_row_per_syllable_with_no_score_drift(self, synthetic_utterance):
        threshold = 58.0
        cached = self._cached_row(synthetic_utterance, threshold)
        rows, span_available = extract_utterance_rows(
            synthetic_utterance, cached, threshold=threshold
        )
        assert len(rows) == 2
        assert {row["word"] for row in rows} == {"他", "好"}
        # The identity check passed (no exception), and span data is real.
        if span_available:
            for row in rows:
                assert isinstance(row["duration_seconds"], float)
                assert row["duration_seconds"] > 0

    def test_raises_on_a_genuine_score_mismatch(self, synthetic_utterance):
        threshold = 58.0
        cached = self._cached_row(synthetic_utterance, threshold)
        cached["characters"][0]["score"] = (
            cached["characters"][0]["score"] + 40
        ) % 100  # deliberately wrong
        with pytest.raises(FrozenScoreMismatchError):
            extract_utterance_rows(synthetic_utterance, cached, threshold=threshold)

    def test_raises_when_a_pass_fail_verdict_would_flip(self, synthetic_utterance):
        """Score drift small enough to survive the float check can still flip
        the verdict right at the threshold — that must be caught too."""
        threshold = 58.0
        cached = self._cached_row(synthetic_utterance, threshold)
        real_score = cached["characters"][0]["score"]
        # Push the cached value to the opposite side of the threshold without
        # tripping the coarse float-diff check first.
        cached["characters"][0]["score"] = 200.0 - real_score if real_score < threshold else 0.0
        with pytest.raises(FrozenScoreMismatchError):
            extract_utterance_rows(synthetic_utterance, cached, threshold=threshold)

    def test_no_cached_row_yields_no_rows_not_an_error(self, synthetic_utterance):
        rows, span_available = extract_utterance_rows(
            synthetic_utterance, None, threshold=58.0
        )
        assert rows == []
        assert span_available is False


class TestUnjudgedWordsAreExcluded:
    """Regression: an early version counted every unjudged word (the analyzer
    declining to score a syllable it had too little pitch evidence for,
    `passed=None`/placeholder `score=0.0`) as a genuine system rejection.

    That silently reproduced, in this export, the exact confusion the
    four-state diagnosis (tone_decision.py) was built to prevent: "the system
    had nothing to say" is not the same claim as "the system said wrong", and
    `error_analysis.build_rows` already excludes unjudged words for that
    reason. This module must apply the identical exclusion.
    """

    def _mocked_word_prosody(self):
        return (
            [],  # pitch_contour placeholder (unused once analyze_all is mocked)
            {}, 1.0, 1.0, {},
            [
                {
                    "token": "他",
                    "syllables": [{"char": "他", "score": 90.0, "passed": True}],
                },
                {
                    # Too few pitch frames to judge -> passed=None, placeholder
                    # score=0.0. This is what `segment_judged=False` looks like
                    # on the wire, per estimate_word_prosody.
                    "token": "好",
                    "syllables": [{"char": "好", "score": 0.0, "passed": None}],
                },
            ],
            1, 90.0, "", {},
        )

    def test_the_unjudged_word_produces_no_row(self, synthetic_utterance):
        utterance = OmpalUtterance(
            utterance_id=synthetic_utterance.utterance_id,
            speaker_id=synthetic_utterance.speaker_id,
            is_native=False,
            text="他好",
            wav_path=synthetic_utterance.wav_path,
            words=(
                OmpalWord(text="他", expected_tones=(1,), rater_tone_labels=(True, True, True)),
                OmpalWord(text="好", expected_tones=(3,), rater_tone_labels=(True, True, True)),
            ),
            rater_accuracy=(4.0,), rater_fluency=(4.0,), rater_prosody=(4.0,),
        )
        cached = {
            "utterance_id": utterance.utterance_id,
            "characters": [
                {"char": "他", "score": 90.0, "judged": True},
                {"char": "好", "score": 0.0, "judged": False},
            ],
            "error": None,
        }
        with patch(
            "benchmarking.diagnostics.analyze_all",
            return_value=self._mocked_word_prosody(),
        ):
            rows, _span = extract_utterance_rows(utterance, cached, threshold=58.0)

        assert [row["word"] for row in rows] == ["他"], (
            "the unjudged 好 must be excluded, not counted as a rejection"
        )
