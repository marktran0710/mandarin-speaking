from analytics.learner_model.vocabulary_state import build_vocabulary_state


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
    assert state["practice"]["unresolvedDimensions"] == ["pinyin"]
    assert state["practice"]["repairProgress"] == {"pinyin": 1}


def test_two_corrective_successes_in_the_failed_dimension_complete_practice():
    history = [
        _row(correct=False, dimension="pinyin_production"),
        _row(correct=True, dimension="meaning"),
        _row(correct=True, dimension="contextual_recall"),
        _row(correct=True, dimension="pinyin_production", activity="personalized_practice"),
        _row(correct=True, dimension="pinyin_production", activity="personalized_practice"),
    ]

    state = _state(history)

    assert state["practice"]["status"] == "COMPLETE"
    assert state["practice"]["unresolvedDimensions"] == []
    assert state["practice"]["repairedDimensions"] == ["pinyin"]
    assert state["review"] == {"status": "STRONG", "candidate": False}


def test_a_success_in_an_unrelated_dimension_does_not_count_toward_the_repair():
    history = [
        _row(correct=False, dimension="pinyin_production"),
        _row(correct=True, dimension="meaning"),
        _row(correct=True, dimension="contextual_recall"),
        _row(correct=True, dimension="meaning", activity="personalized_practice"),
        _row(correct=True, dimension="pinyin_production", activity="personalized_practice"),
    ]

    state = _state(history)

    assert state["practice"]["unresolvedDimensions"] == ["pinyin"]
    assert state["practice"]["repairProgress"] == {"pinyin": 1}
    assert state["practice"]["status"] == "IN_PROGRESS"


def test_each_dimension_has_its_own_bkt_probability_and_response_evidence():
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
    assert state["bkt"]["dimensions"]["meaning"]["pLearned"] == 0.4
    assert state["bkt"]["dimensions"]["meaning"]["observationCount"] == 2
    assert state["bkt"]["dimensions"]["pinyin"]["pLearned"] == 0.4
    assert state["bkt"]["dimensions"]["context"]["pLearned"] == 0.4


def test_runtime_replays_each_bkt_component_from_only_its_own_responses():
    from analytics.learner_model.bkt.core import BKT_CONFIG, replay_bkt_typed
    from analytics.learner_model.bkt.mastery import _mastery_states_from_responses

    responses = [
        {
            "word_id": "same-word",
            "item_id": f"item-{dimension}",
            "question_type": question_type,
            "knowledge_dimension": dimension,
            "correct": correct,
            "occurred_at": f"2026-09-0{index}T00:00:00+00:00",
            "bkt_eligible": False,
            "diagnostic_exposure_id": None,
            "activity_type": "diagnostic",
            "round_type": None,
            "lesson_id": "lesson-1",
        }
        for index, (dimension, question_type, correct) in enumerate((
            ("meaning", "basic_meaning_mcq", True),
            ("pinyin_production", "character_to_pinyin_typing", False),
            ("contextual_recall", "context_cloze_mcq", True),
        ), start=1)
    ]

    state = _mastery_states_from_responses(responses, BKT_CONFIG)["same-word"]

    assert state["dimension_states"]["meaning"]["pLearned"] == replay_bkt_typed([(True, "basic_meaning_mcq")])
    assert state["dimension_states"]["pinyin"]["pLearned"] == replay_bkt_typed([(False, "character_to_pinyin_typing")])
    assert state["dimension_states"]["context"]["pLearned"] == replay_bkt_typed([(True, "context_cloze_mcq")])
    assert [state["dimension_states"][key]["observationCount"] for key in ("meaning", "pinyin", "context")] == [1, 1, 1]
    assert state["p_learned"] == replay_bkt_typed([
        (True, "basic_meaning_mcq"),
        (False, "character_to_pinyin_typing"),
        (True, "context_cloze_mcq"),
    ])


def test_wrong_dimension_successes_do_not_satisfy_targeted_practice_requirement():
    history = [
        _row(correct=False, dimension="pinyin_production"),
        _row(correct=True, dimension="meaning"),
        _row(correct=True, dimension="contextual_recall"),
        _row(correct=True, dimension="meaning", activity="personalized_practice"),
        _row(correct=True, dimension="contextual_recall", activity="personalized_practice"),
    ]

    state = _state(history)

    assert state["practice"]["unresolvedDimensions"] == ["pinyin"]
    assert state["practice"]["repairProgress"] == {"pinyin": 0}
    assert state["practice"]["status"] == "IN_PROGRESS"
    assert state["review"]["status"] == "NEEDS_PRACTICE"


def test_maintenance_failure_opens_corrective_practice_for_that_dimension():
    history = [
        _row(correct=True, dimension="meaning"),
        _row(correct=False, dimension="contextual_recall", activity="scheduled_maintenance"),
        _row(correct=True, dimension="contextual_recall", activity="personalized_practice"),
        _row(correct=True, dimension="contextual_recall", activity="personalized_practice"),
    ]

    state = _state(history)

    assert state["practice"]["repairedDimensions"] == ["context"]
    assert state["practice"]["unresolvedDimensions"] == []
    assert state["practice"]["status"] == "COMPLETE"


def test_later_maintenance_failure_reopens_a_completed_corrective_epoch():
    history = [
        _row(correct=False, dimension="contextual_recall"),
        _row(correct=True, dimension="contextual_recall", activity="personalized_practice"),
        _row(correct=True, dimension="contextual_recall", activity="personalized_practice"),
        _row(correct=False, dimension="contextual_recall", activity="scheduled_maintenance"),
    ]

    reopened = _state(history)

    assert reopened["practice"]["status"] == "IN_PROGRESS"
    assert reopened["practice"]["unresolvedDimensions"] == ["context"]
    assert reopened["practice"]["repairProgress"] == {"context": 0}
    assert reopened["review"] == {"status": "NEEDS_PRACTICE", "candidate": True}

    completed = _state(history + [
        _row(correct=True, dimension="contextual_recall", activity="personalized_practice"),
        _row(correct=True, dimension="contextual_recall", activity="personalized_practice"),
    ])
    assert completed["practice"]["status"] == "COMPLETE"
    assert completed["practice"]["unresolvedDimensions"] == []


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

    assert state["practice"]["unresolvedDimensions"] == ["pinyin"]
    assert state["practice"]["nextDimension"] == "pinyin"
    assert state["practice"]["status"] == "IN_PROGRESS"


def test_successful_voluntary_practice_does_not_demote_a_strong_word():
    state = _state([
        _row(correct=True, dimension="meaning"),
        _row(correct=True, dimension="pinyin_production"),
        _row(correct=True, dimension="contextual_recall"),
        _row(correct=True, dimension="contextual_recall", activity="personalized_practice"),
    ])

    assert state["practice"]["status"] == "NOT_REQUIRED"
    assert state["review"] == {"status": "STRONG", "candidate": False}
