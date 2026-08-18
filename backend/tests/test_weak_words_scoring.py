"""Unit tests for the ability+accuracy+time+history weak-word scorer."""

from analytics.weak_words import WordOccurrence, score_weak_words


def _occ(correct: bool, time_ms: int = 2000) -> WordOccurrence:
    return WordOccurrence(correct=correct, time_ms=time_ms)


def test_word_wrong_on_the_most_recent_attempt_is_always_weak():
    # Even with a decent history and no ability gap, the most recent
    # attempt being wrong must always flag the word — this is the floor
    # the old "wrong last time" behavior guaranteed.
    occurrences = {"word": [_occ(True), _occ(True), _occ(True), _occ(False)]}
    scores = score_weak_words(occurrences, ability=2.0, speed=0.0,
                               difficulty_by_word={}, time_intensity_by_word={})
    assert scores[0].weak is True


def test_single_exposure_falls_back_to_simple_wrong_last_time_rule():
    # Below MIN_EXPOSURES_FOR_MODEL there isn't enough history to trust an
    # ability-adjusted gap — a single correct answer should not be flagged
    # weak just because the model has no other evidence either way.
    occurrences = {"word": [_occ(True)]}
    scores = score_weak_words(occurrences, ability=0.0, speed=0.0,
                               difficulty_by_word={}, time_intensity_by_word={})
    assert scores[0].weak is False
    assert scores[0].exposures == 1


def test_a_high_ability_student_missing_an_easy_word_scores_weaker_than_average():
    # ability=3 (strong student), difficulty=-3 (very easy word): expected
    # accuracy is near-certain, so even two out of three correct should
    # read as a real gap, not noise.
    occurrences = {
        "word": [_occ(True), _occ(False), _occ(True)],
    }
    scores = score_weak_words(
        occurrences, ability=3.0, speed=0.0,
        difficulty_by_word={"word": -3.0}, time_intensity_by_word={},
    )
    assert scores[0].p_expected > 0.99
    assert scores[0].weak is True


def test_correct_last_time_but_far_below_expected_accuracy_is_flagged():
    # Word answered correctly most recently, but the recency-weighted
    # accuracy across history is well below what this student's ability
    # predicts for an easy word — the new capability the binary rule
    # couldn't express.
    occurrences = {
        "word": [_occ(False), _occ(False), _occ(False), _occ(True)],
    }
    scores = score_weak_words(
        occurrences, ability=3.0, speed=0.0,
        difficulty_by_word={"word": -3.0}, time_intensity_by_word={},
    )
    assert scores[0].weak is True
    assert scores[0].weak_score > 0


def test_unusually_slow_correct_answers_contribute_a_time_flag():
    # Two words, both always correct, same ability/difficulty (so gap is
    # ~0 for both) — but "slow" takes far longer than this student's own
    # norm on "fast". Only the slow one should be flagged.
    occurrences = {
        "fast": [_occ(True, 1500), _occ(True, 1500)],
        "slow": [_occ(True, 9000), _occ(True, 9000)],
    }
    scores = score_weak_words(
        occurrences, ability=0.0, speed=0.0,
        difficulty_by_word={"fast": 0.0, "slow": 0.0},
        time_intensity_by_word={"fast": 0.0, "slow": 0.0},
    )
    by_word = {s.word: s for s in scores}
    assert by_word["slow"].weak is True
    assert by_word["fast"].weak is False


def test_unknown_word_and_student_default_to_average_difficulty_and_ability():
    # A word/student missing from the fit (e.g. brand new) shouldn't crash
    # — defaults to difficulty=0/ability=0 (average).
    occurrences = {"word": [_occ(True), _occ(True)]}
    scores = score_weak_words(occurrences, ability=0.0, speed=0.0,
                               difficulty_by_word={}, time_intensity_by_word={})
    assert scores[0].p_expected == 0.5
