from analytics.vocabulary_state import build_vocabulary_state


def _row(*, correct: bool, dimension: str | None, activity: str = "diagnostic") -> dict:
    return {
        "correct": correct,
        "knowledge_dimension": dimension,
        "activity_type": activity,
        "question_type": "basic_meaning_mcq",
        "occurred_at": "2026-09-17T00:00:00+00:00",
    }


def _state(history: list[dict], p_learned: float = 0.98) -> dict:
    return build_vocabulary_state(
        history=history,
        p_learned=p_learned,
        observation_count=len(history),
        diagnostic_complete=True,
        mastery_threshold=0.95,
        minimum_observations=3,
        model_version="test-bkt",
        parameter_fingerprint="test-fingerprint",
    )


def test_one_corrective_success_does_not_complete_practice_after_bkt_crosses_threshold():
    history = [
        _row(correct=False, dimension="pinyin_production"),
        _row(correct=True, dimension="meaning"),
        _row(correct=True, dimension="contextual_recall"),
        _row(correct=True, dimension="pinyin_production", activity="personalized_practice"),
    ]

    state = _state(history)

    assert state["bkt"]["status"] == "STRONG"
    assert state["review"] == {"status": "NEEDS_PRACTICE", "candidate": True}
    assert state["practice"]["status"] == "IN_PROGRESS"
    assert state["practice"]["correctiveSuccesses"] == 1
    assert state["practice"]["targetedSuccess"] is True


def test_two_corrective_successes_including_failed_dimension_complete_practice():
    history = [
        _row(correct=False, dimension="pinyin_production"),
        _row(correct=True, dimension="meaning"),
        _row(correct=True, dimension="contextual_recall"),
        _row(correct=True, dimension="meaning", activity="personalized_practice"),
        _row(correct=True, dimension="pinyin_production", activity="personalized_practice"),
    ]

    state = _state(history)

    assert state["practice"]["status"] == "COMPLETE"
    assert state["practice"]["correctiveSuccesses"] == 2
    assert state["practice"]["failedDimensions"] == ["pinyin"]
    assert state["practice"]["targetedSuccess"] is True
    assert state["review"] == {"status": "STRONG", "candidate": False}


def test_dimension_evidence_is_persisted_as_explanatory_state_not_separate_bkt_probabilities():
    state = _state([
        _row(correct=False, dimension="meaning"),
        _row(correct=True, dimension="pinyin_production"),
        _row(correct=True, dimension="contextual_recall"),
        _row(correct=True, dimension=None),
    ], p_learned=0.4)

    assert state["evidence"]["total"] == 4
    assert state["evidence"]["correct"] == 3
    assert state["evidence"]["byDimension"]["meaning"]["incorrect"] == 1
    assert state["evidence"]["byDimension"]["pinyin"]["correct"] == 1
    assert state["evidence"]["byDimension"]["context"]["correct"] == 1
    assert set(state["bkt"]) == {"pLearned", "status", "modelVersion", "parameterFingerprint"}


def test_wrong_dimension_successes_do_not_satisfy_targeted_practice_requirement():
    history = [
        _row(correct=False, dimension="pinyin_production"),
        _row(correct=True, dimension="meaning"),
        _row(correct=True, dimension="contextual_recall"),
        _row(correct=True, dimension="meaning", activity="personalized_practice"),
        _row(correct=True, dimension="contextual_recall", activity="personalized_practice"),
    ]

    state = _state(history)

    assert state["practice"]["correctiveSuccesses"] == 2
    assert state["practice"]["targetedSuccess"] is False
    assert state["practice"]["status"] == "IN_PROGRESS"
    assert state["review"]["status"] == "NEEDS_PRACTICE"


def test_maintenance_failure_opens_corrective_practice_for_that_dimension():
    history = [
        _row(correct=True, dimension="meaning"),
        _row(correct=False, dimension="contextual_recall", activity="scheduled_maintenance"),
        _row(correct=True, dimension="meaning", activity="personalized_practice"),
        _row(correct=True, dimension="contextual_recall", activity="personalized_practice"),
    ]

    state = _state(history)

    assert state["practice"]["failedDimensions"] == ["context"]
    assert state["practice"]["targetedSuccess"] is True
    assert state["practice"]["status"] == "COMPLETE"
    assert state["review"] == {"status": "STRONG", "candidate": False}


def test_later_maintenance_failure_reopens_a_completed_corrective_epoch():
    history = [
        _row(correct=False, dimension="contextual_recall"),
        _row(correct=True, dimension="contextual_recall", activity="personalized_practice"),
        _row(correct=True, dimension="meaning", activity="personalized_practice"),
        _row(correct=False, dimension="contextual_recall", activity="scheduled_maintenance"),
    ]

    reopened = _state(history)

    assert reopened["practice"]["status"] == "IN_PROGRESS"
    assert reopened["practice"]["correctiveSuccesses"] == 0
    assert reopened["practice"]["targetedSuccess"] is False
    assert reopened["review"] == {"status": "NEEDS_PRACTICE", "candidate": True}

    completed = _state(history + [
        _row(correct=True, dimension="contextual_recall", activity="personalized_practice"),
        _row(correct=True, dimension="meaning", activity="personalized_practice"),
    ])
    assert completed["practice"]["status"] == "COMPLETE"
    assert completed["practice"]["correctiveSuccesses"] == 2


def test_reopened_epoch_must_target_the_latest_failed_dimension():
    history = [
        _row(correct=False, dimension="meaning"),
        _row(correct=True, dimension="meaning", activity="personalized_practice"),
        _row(correct=True, dimension="meaning", activity="personalized_practice"),
        _row(correct=False, dimension="pinyin_production", activity="scheduled_maintenance"),
        _row(correct=True, dimension="meaning", activity="personalized_practice"),
        _row(correct=True, dimension="meaning", activity="personalized_practice"),
    ]

    state = _state(history)

    assert state["practice"]["failedDimensions"] == ["pinyin"]
    assert state["practice"]["correctiveSuccesses"] == 2
    assert state["practice"]["targetedSuccess"] is False
    assert state["practice"]["status"] == "IN_PROGRESS"


def test_successful_voluntary_practice_does_not_demote_a_strong_word():
    state = _state([
        _row(correct=True, dimension="meaning"),
        _row(correct=True, dimension="contextual_recall"),
        _row(correct=True, dimension="contextual_recall", activity="personalized_practice"),
    ])

    assert state["practice"]["status"] == "NOT_REQUIRED"
    assert state["review"] == {"status": "STRONG", "candidate": False}
