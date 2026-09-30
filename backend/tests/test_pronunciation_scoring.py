"""The deterministic /100 score: same measurements in, same number out."""

import dataclasses

import pytest

from domain.pronunciation.compare import compare_utterances
from domain.pronunciation.policy import DimensionWeights, PronunciationScoringPolicy
from domain.pronunciation.scoring import apportion, score_comparison
from pron_fixtures import make_utterance

SHAPES = ["fall", "rise", "dip", "flat"]
REFERENCE = make_utterance(SHAPES)


def _score(student, reference=REFERENCE, policy=None):
    policy = policy or PronunciationScoringPolicy()
    return score_comparison(compare_utterances(student, reference, policy), policy)


def test_the_same_measurements_always_produce_the_same_score():
    student = make_utterance(["flat", "rise", "dip", "flat"], pauses_after={1: 300})
    first = _score(student)
    for _ in range(5):
        assert _score(student) == first


def test_a_perfect_imitation_scores_100():
    result = _score(make_utterance(SHAPES))
    assert result.status == "scored"
    assert result.total == 100
    assert result.issues == ()


def test_unmeasurable_dimensions_are_reported_unavailable_not_invented():
    result = _score(make_utterance(SHAPES))
    by_key = {d.key: d for d in result.dimensions}
    for key in ("segmental", "intelligibility"):
        assert by_key[key].basis == "unavailable"
        assert by_key[key].points is None and by_key[key].max_points is None
    assert by_key["tone"].basis == "measured"
    assert by_key["fluency"].basis == "measured"
    assert result.renormalized is True


def test_total_is_renormalised_over_the_measured_dimensions_and_adds_up():
    result = _score(make_utterance(["flat", "rise", "dip", "flat"]))
    measured = [d for d in result.dimensions if d.basis != "unavailable"]
    assert sum(d.max_points for d in measured) == 100
    assert sum(d.points for d in measured) == result.total
    # Default weights tone .4 : fluency .2 -> 67 : 33 once the rest is unavailable.
    assert {d.key: d.max_points for d in measured} == {"tone": 67, "fluency": 33}


def test_weights_are_configurable_and_change_the_split():
    policy = dataclasses.replace(
        PronunciationScoringPolicy(),
        weights=DimensionWeights(tone=0.5, fluency=0.5, segmental=0.0, intelligibility=0.0),
    )
    result = _score(make_utterance(SHAPES), policy=policy)
    assert {d.key: d.max_points for d in result.dimensions if d.max_points} == {"tone": 50, "fluency": 50}


@pytest.mark.parametrize("weights", [(0.4, 0.2), (1, 1), (0.7, 0.3), (1, 2), (3, 3)])
def test_apportion_always_sums_to_the_target(weights):
    assert sum(apportion(list(weights), 100)) == 100


def test_a_correct_fourth_tone_beats_a_flat_one_which_beats_nothing_like_it():
    reference = make_utterance(["fall", "rise", "fall", "rise"])
    correct = _score(make_utterance(["fall", "rise", "fall", "rise"]), reference).total
    one_flat = _score(make_utterance(["flat", "rise", "fall", "rise"]), reference).total
    all_wrong = _score(make_utterance(["rise", "fall", "rise", "fall"]), reference).total
    assert correct > one_flat > all_wrong
    assert correct == 100


def test_a_different_voice_range_does_not_lower_the_score():
    assert _score(make_utterance(SHAPES, offset_st=9.0)).total == _score(make_utterance(SHAPES)).total


def test_natural_speech_slower_than_the_textbook_is_not_marked_down():
    assert _score(make_utterance(SHAPES, syllable_ms=390)).total == 100


def test_a_flat_tone_becomes_a_high_severity_issue_with_its_evidence():
    reference = make_utterance(["fall", "rise"])
    result = _score(make_utterance(["flat", "rise"]), reference)
    assert len(result.issues) == 1
    issue = result.issues[0]
    assert issue.code == "tone_contour_too_flat"
    assert issue.severity == "high"
    assert issue.hanzi == "友"
    assert issue.expected_tone == 4
    assert issue.evidence == "strong"
    assert issue.tone_similarity < 0.2
    # The measured pitch directions travel with the issue so feedback can cite them.
    assert (issue.reference_direction, issue.student_direction) == ("fall", "flat")


def test_issues_are_ranked_most_important_first():
    reference = make_utterance(["fall", "rise", "dip", "fall"])
    student = make_utterance(
        ["fall", "rise", "dip", "fall"], durations=[300, 300, 300, 1400]
    )
    student_flat = make_utterance(["fall", "flat", "dip", "fall"], durations=[300, 300, 300, 300])
    issues = _score(student_flat, reference).issues
    assert issues and issues[0].severity == "high"
    assert [i.severity for i in issues] == sorted(
        (i.severity for i in issues), key={"high": 0, "medium": 1, "low": 2}.get
    )
    # A merely long syllable is ranked below a missing tone contour.
    duration_only = _score(student, reference).issues
    assert all(i.code != "tone_contour_too_flat" for i in duration_only)


def test_a_recording_with_no_measurable_tone_is_unscorable_not_zero():
    reference = make_utterance(["neutral", "neutral"])
    result = _score(make_utterance(["neutral", "neutral"]), reference)
    assert result.status == "unscorable"
    assert result.reason == "no_measurable_tones"
    assert result.total is None and result.dimensions == ()


def test_an_implausible_speaking_rate_is_unscorable():
    # 4 syllables in well over 30 s of speech cannot be this sentence spoken aloud.
    result = _score(make_utterance(SHAPES, syllable_ms=12000))
    assert result.status == "unscorable"
    assert result.reason == "speaking_rate_implausible"


def test_score_carries_the_policy_version_that_produced_it():
    assert _score(make_utterance(SHAPES)).policy_version == "pronunciation-score-v1"
