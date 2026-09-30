"""Feature types: one schema for reference and student, JSON round-trippable."""

import json

import pytest

from domain.pronunciation.types import (
    ExpectedSyllable,
    UtteranceFeatures,
    build_syllable_features,
)
from pron_fixtures import make_utterance


def test_utterance_features_survive_a_json_round_trip_unchanged():
    features = make_utterance(["fall", "rise", "dip"], words=[0, 0, 1], pauses_after={0: 250})
    restored = UtteranceFeatures.from_dict(json.loads(json.dumps(features.to_dict())))
    assert restored == features


def test_build_syllable_features_summarises_a_falling_contour():
    expected = ExpectedSyllable(
        index=0, hanzi="要", pinyin="yao4", citation_tone=4, expected_tone=4,
        accepted_tones=(4,), word_index=0,
    )
    points = [(i * 10, 4.0 - 8.0 * i / 29) for i in range(30)]
    syllable = build_syllable_features(expected, 0, 300, points, intensity_mean=0.8)
    assert syllable.direction == "fall"
    assert syllable.f0_start > syllable.f0_mid > syllable.f0_end
    assert syllable.voiced_ratio == pytest.approx(1.0, abs=0.05)
    assert syllable.duration_ms == 300
    assert syllable.intensity_mean == 0.8


def test_a_syllable_with_no_voiced_pitch_is_reported_as_unvoiced_not_guessed():
    expected = ExpectedSyllable(
        index=0, hanzi="的", pinyin="de5", citation_tone=5, expected_tone=5,
        accepted_tones=(5,), word_index=0,
    )
    syllable = build_syllable_features(expected, 0, 200, [], intensity_mean=None)
    assert syllable.direction == "unvoiced"
    assert syllable.voiced_ratio == 0.0
    assert syllable.f0_start is None and syllable.f0_end is None


def test_neutral_tone_has_no_contour_target():
    neutral = ExpectedSyllable(
        index=0, hanzi="麼", pinyin="me5", citation_tone=5, expected_tone=5,
        accepted_tones=(5,), word_index=0,
    )
    optional = ExpectedSyllable(
        index=1, hanzi="麼", pinyin="me5", citation_tone=4, expected_tone=4,
        accepted_tones=(4, 5), word_index=0,
    )
    assert neutral.measurable_by_contour is False
    # A tone that may also be said neutral still has a contour to compare.
    assert optional.measurable_by_contour is True
