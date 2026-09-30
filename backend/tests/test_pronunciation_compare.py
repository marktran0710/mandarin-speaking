"""Student-vs-reference comparison: measurable evidence only, no scoring."""

import pytest

from domain.pronunciation.compare import ReferenceMismatchError, compare_utterances
from pron_fixtures import make_utterance

SHAPES = ["fall", "rise", "dip", "flat"]


def _compare(student, reference):
    return compare_utterances(student, reference)


def test_an_identical_utterance_matches_on_every_measure():
    reference = make_utterance(SHAPES)
    result = _compare(make_utterance(SHAPES), reference)
    assert result.tone_similarity > 0.95
    assert result.rhythm_similarity == pytest.approx(1.0)
    assert result.pause_similarity == pytest.approx(1.0)
    assert result.duration_similarity == pytest.approx(1.0)
    assert all(not s.flags for s in result.syllables)


def test_a_different_voice_range_is_not_penalised():
    reference = make_utterance(SHAPES)
    same_voice = _compare(make_utterance(SHAPES), reference)
    other_voice = _compare(make_utterance(SHAPES, offset_st=9.0), reference)
    assert other_voice.tone_similarity == pytest.approx(same_voice.tone_similarity)
    assert all(not s.flags for s in other_voice.syllables)


def test_flat_fourth_tone_is_flagged_as_too_flat_against_a_falling_reference():
    reference = make_utterance(["fall", "rise"])
    student = make_utterance(["flat", "rise"])
    result = _compare(student, reference)
    first = result.syllables[0]
    assert first.reference_direction == "fall"
    assert first.student_direction == "flat"
    assert "tone_contour_too_flat" in first.flags
    assert first.tone_similarity < 0.2
    assert result.syllables[1].flags == ()


def test_a_rising_contour_where_a_fall_is_expected_is_a_direction_mismatch():
    reference = make_utterance(["fall", "rise"])
    student = make_utterance(["rise", "rise"])
    first = _compare(student, reference).syllables[0]
    assert "tone_direction_mismatch" in first.flags


def test_a_correct_fall_outscores_both_a_flat_and_a_wrong_direction_attempt():
    reference = make_utterance(["fall", "rise"])
    correct = _compare(make_utterance(["fall", "rise"]), reference).syllables[0].tone_similarity
    flat = _compare(make_utterance(["flat", "rise"]), reference).syllables[0].tone_similarity
    wrong = _compare(make_utterance(["rise", "rise"]), reference).syllables[0].tone_similarity
    assert correct > 0.9
    assert correct - flat > 0.6
    assert correct - wrong > 0.6


def test_a_level_tone_performed_with_movement_is_flagged():
    reference = make_utterance(["flat", "rise"])
    student = make_utterance(["fall", "rise"])
    first = _compare(student, reference).syllables[0]
    assert "tone_contour_not_level" in first.flags


def test_a_narrower_movement_in_the_right_direction_is_flagged_as_narrow():
    reference = make_utterance(["fall", "rise"])
    student = make_utterance(["fall", "rise"], scale=0.35)
    first = _compare(student, reference).syllables[0]
    assert "tone_range_too_narrow" in first.flags


def test_the_right_direction_with_a_different_shape_is_flagged_but_not_with_full_confidence():
    reference = make_utterance(["dip", "rise"])
    student = make_utterance(["wide_dip", "rise"])
    first = _compare(student, reference).syllables[0]
    assert (first.reference_direction, first.student_direction) == ("dip", "dip")
    assert first.tone_similarity < 0.6
    # A low score must never be unexplained: the difference is named, but direction
    # agrees so it is not stated as confidently as a missing or reversed tone.
    assert first.flags == ("tone_shape_differs",)
    assert first.evidence == "moderate"


def test_slower_speech_than_the_textbook_does_not_hurt_rhythm_or_tone():
    reference = make_utterance(SHAPES)
    slow = make_utterance(SHAPES, syllable_ms=390)  # 1.3x slower, within the textbook-slack band
    result = _compare(slow, reference)
    assert result.rhythm_similarity == pytest.approx(1.0)
    assert result.duration_similarity == pytest.approx(1.0)
    assert result.tone_similarity > 0.95
    assert result.speaking_rate_ratio == pytest.approx(1 / 1.3, rel=0.01)


def test_very_slow_speech_loses_a_little_duration_credit_only():
    reference = make_utterance(SHAPES)
    very_slow = make_utterance(SHAPES, syllable_ms=540)  # 1.8x slower
    result = _compare(very_slow, reference)
    assert 0.7 < result.duration_similarity < 1.0
    assert result.rhythm_similarity == pytest.approx(1.0)


def test_one_stretched_syllable_is_a_rhythm_problem_and_is_flagged():
    reference = make_utterance(SHAPES)
    # Durations are judged against the utterance's own mean, so the stretch has
    # to be large enough to stand out from the average it is part of.
    student = make_utterance(SHAPES, durations=[300, 300, 1200, 300])
    result = _compare(student, reference)
    assert result.rhythm_similarity < 0.9
    assert "syllable_too_long" in result.syllables[2].flags
    assert result.syllables[2].duration_ratio > 2.0


def test_a_pause_where_the_reference_also_pauses_is_not_penalised():
    reference = make_utterance(SHAPES, pauses_after={1: 300})
    student = make_utterance(SHAPES, pauses_after={1: 200})
    assert _compare(student, reference).pause_similarity == pytest.approx(1.0)


def test_an_extra_mid_phrase_pause_lowers_pause_similarity():
    reference = make_utterance(SHAPES)
    choppy = make_utterance(SHAPES, pauses_after={0: 300, 2: 300})
    assert _compare(choppy, reference).pause_similarity < 0.5


def test_missing_a_textbook_pause_costs_little():
    reference = make_utterance(SHAPES, pauses_after={1: 300})
    student = make_utterance(SHAPES)
    assert 0.8 <= _compare(student, reference).pause_similarity < 1.0


def test_words_are_compared_as_whole_contours_and_drive_the_tone_score():
    reference = make_utterance(["fall", "rise", "dip"], words=[0, 0, 1])
    result = _compare(make_utterance(["fall", "rise", "dip"], words=[0, 0, 1]), reference)
    assert [w.syllable_indices for w in result.words] == [(0, 1), (2,)]
    assert all(w.judged for w in result.words)
    assert result.judged_words == 2 and result.total_words == 2


def test_a_neutral_tone_syllable_is_not_judged():
    reference = make_utterance(["fall", "neutral"], words=[0, 0])
    result = _compare(make_utterance(["fall", "neutral"], words=[0, 0]), reference)
    assert result.syllables[1].judged is False
    assert result.syllables[1].tone_similarity is None


def test_evidence_is_strongest_for_single_syllable_words_and_weak_for_long_ones():
    reference = make_utterance(["fall", "rise", "fall", "rise", "fall"], words=[0, 1, 1, 2, 2])
    student = make_utterance(["flat", "flat", "flat", "flat", "flat"], words=[0, 1, 1, 2, 2])
    result = _compare(student, reference)
    assert result.syllables[0].evidence == "strong"  # one-syllable word
    assert result.syllables[1].evidence == "moderate"  # two-syllable word


def test_low_alignment_confidence_caps_all_evidence_at_weak():
    reference = make_utterance(["fall", "rise"])
    student = make_utterance(["flat", "rise"], alignment_confidence=0.2)
    result = _compare(student, reference)
    assert result.syllables[0].evidence == "weak"


def test_comparing_different_sentences_is_refused():
    with pytest.raises(ReferenceMismatchError):
        _compare(make_utterance(["fall", "rise"], text="友美"), make_utterance(["fall", "rise"], text="你好"))


def test_comparing_different_syllable_counts_is_refused():
    with pytest.raises(ReferenceMismatchError):
        _compare(make_utterance(["fall"]), make_utterance(["fall", "rise"]))
