"""Corrective-practice state for the single pooled word-level BKT flow.

One P(Learned) per word (unchanged).  Beside it, `unresolvedDimensions` is the
single source of truth for "which required dimension still needs repair"; the
backend completion gate and the frontend question selector both read it.

Histories are built from compact (activity, dimension, correct) triples and the
pooled P(Learned) is produced by the real format-aware replay, so every
"P(Learned) > .95" claim below is the model's own number.
"""

import pytest

from analytics.learner_model.bkt.core import BKT_CONFIG, replay_bkt_typed
from analytics.learner_model.vocabulary_state import (
    build_vocabulary_state,
    corrective_trace,
    select_corrective_dimension,
    unresolved_dimensions,
)

_QUESTION_TYPE = {
    "meaning": "basic_meaning_mcq",
    "pinyin": "character_to_pinyin_typing",
    "context": "context_cloze_mcq",
}
_KNOWLEDGE_DIMENSION = {"meaning": "meaning", "pinyin": "pinyin_production", "context": "contextual_recall"}


def _history(*steps: tuple[str, str, bool]) -> list[dict]:
    """(activity, dimension, correct) -> ledger-shaped rows, in order."""
    return [
        {
            "activity_type": activity,
            "knowledge_dimension": _KNOWLEDGE_DIMENSION[dimension],
            "question_type": _QUESTION_TYPE[dimension],
            "correct": correct,
            "occurred_at": f"2026-09-{index + 1:02d}T00:00:00+00:00",
            "item_id": f"item-{index}",
        }
        for index, (activity, dimension, correct) in enumerate(steps)
    ]


def _state(history: list[dict], *, diagnostic_complete: bool = True, minimum_observations: int = 3) -> dict:
    p_learned = replay_bkt_typed(
        ((row["correct"], row["question_type"]) for row in history), BKT_CONFIG,
    )
    return build_vocabulary_state(
        history=history,
        p_learned=p_learned,
        observation_count=len(history),
        diagnostic_complete=diagnostic_complete,
        mastery_threshold=BKT_CONFIG.mastery_threshold,
        minimum_observations=minimum_observations,
        model_version="test-bkt",
        parameter_fingerprint="test-fingerprint",
    )


D = "diagnostic"
P = "personalized_practice"
M = "scheduled_maintenance"


# ---- Case A: every diagnostic correct --------------------------------------

def test_case_a_all_diagnostics_correct_is_strong_with_nothing_unresolved():
    state = _state(_history((D, "meaning", True), (D, "pinyin", True), (D, "context", True)))

    assert state["diagnostic"]["coverageComplete"] is True
    assert state["practice"]["unresolvedDimensions"] == []
    assert state["practice"]["nextDimension"] is None
    assert state["practice"]["status"] == "NOT_REQUIRED"
    assert state["review"] == {"status": "STRONG", "candidate": False}


def test_strong_requires_minimum_observations():
    history = _history((D, "meaning", True), (D, "pinyin", True), (D, "context", True))

    state = _state(history, minimum_observations=4)

    assert state["bkt"]["pLearned"] >= BKT_CONFIG.mastery_threshold
    assert state["review"]["status"] == "NEEDS_PRACTICE"


def test_strong_requires_every_dimension_to_have_been_observed():
    # High P(Learned) built from meaning + context only: pinyin was never covered.
    history = _history(
        (D, "meaning", True), (D, "context", True), (P, "meaning", True), (P, "context", True),
    )

    state = _state(history)

    assert state["bkt"]["pLearned"] >= BKT_CONFIG.mastery_threshold
    assert state["diagnostic"]["coverageComplete"] is False
    assert state["review"]["status"] == "NEEDS_PRACTICE"
    assert state["practice"]["nextDimension"] == "pinyin"
    assert state["practice"]["selectionReason"] == "complete_coverage"


def test_strong_requires_the_lesson_diagnostic_to_be_complete():
    history = _history((D, "meaning", True), (D, "pinyin", True), (D, "context", True))

    state = _state(history, diagnostic_complete=False)

    assert state["review"]["status"] == "PROVISIONAL_REVIEW"


# ---- Case B: one failed dimension ------------------------------------------

def test_case_b_single_failed_dimension_is_unresolved_and_selected():
    state = _state(_history((D, "meaning", False), (D, "pinyin", True), (D, "context", True)))

    assert state["practice"]["unresolvedDimensions"] == ["meaning"]
    assert state["practice"]["nextDimension"] == "meaning"
    assert state["practice"]["selectionReason"] == "repair_unresolved"
    assert state["review"] == {"status": "NEEDS_PRACTICE", "candidate": True}


def test_placement_failure_initializes_bkt_but_does_not_create_corrective_debt():
    placement = _history((D, "meaning", False))[0]
    placement.update({
        "diagnostic_exposure_id": "placement:attempt-1:item-1",
        "resolver_version": "placement-assessment-v1",
        "evidence_origin": "real",
        "bkt_eligible": True,
    })
    learned = _history(
        (D, "meaning", True), (D, "pinyin", True), (D, "context", True),
    )

    state = _state([placement, *learned])

    assert state["practice"]["unresolvedDimensions"] == []
    assert state["practice"]["status"] == "NOT_REQUIRED"
    assert state["review"]["status"] == "STRONG"


def test_case_b_word_becomes_strong_only_after_the_dimension_is_repaired():
    base = [(D, "meaning", False), (D, "pinyin", True), (D, "context", True)]

    one = _state(_history(*base, (P, "meaning", True)))
    assert one["practice"]["unresolvedDimensions"] == ["meaning"]
    assert one["practice"]["repairProgress"] == {"meaning": 1}
    assert one["review"]["status"] == "NEEDS_PRACTICE"

    two = _state(_history(*base, (P, "meaning", True), (P, "meaning", True)))
    assert two["practice"]["unresolvedDimensions"] == []
    assert two["practice"]["status"] == "COMPLETE"
    assert two["review"] == {"status": "STRONG", "candidate": False}


# ---- Case C: several failed dimensions -------------------------------------

def test_case_c_two_failed_dimensions_are_repaired_in_stable_order():
    base = [(D, "meaning", False), (D, "pinyin", False), (D, "context", True)]

    start = _state(_history(*base))
    assert start["practice"]["unresolvedDimensions"] == ["meaning", "pinyin"]
    assert start["practice"]["nextDimension"] == "meaning"

    meaning_fixed = _state(_history(*base, (P, "meaning", True), (P, "meaning", True)))
    # Repairing meaning must NOT erase the pinyin requirement.
    assert meaning_fixed["practice"]["unresolvedDimensions"] == ["pinyin"]
    assert meaning_fixed["practice"]["nextDimension"] == "pinyin"
    assert meaning_fixed["practice"]["status"] == "IN_PROGRESS"
    assert meaning_fixed["review"]["status"] == "NEEDS_PRACTICE"

    both = _state(_history(
        *base, (P, "meaning", True), (P, "meaning", True), (P, "pinyin", True), (P, "pinyin", True),
    ))
    assert both["practice"]["unresolvedDimensions"] == []
    assert both["practice"]["status"] == "COMPLETE"
    assert both["review"]["status"] == "STRONG"


def test_case_c_late_failure_repair_cannot_hide_an_older_unresolved_dimension():
    # docs/bkt-code-review.md finding 2: meaning wrong, context right, pinyin
    # wrong, then three correct pinyin practice answers.
    history = _history(
        (D, "meaning", False), (D, "context", True), (D, "pinyin", False),
        (P, "pinyin", True), (P, "pinyin", True), (P, "pinyin", True),
    )

    state = _state(history)

    assert state["practice"]["unresolvedDimensions"] == ["meaning"]
    assert state["practice"]["status"] != "COMPLETE"
    assert state["review"]["status"] == "NEEDS_PRACTICE"


# ---- Case D: a repaired historical failure is not selected again ------------

def test_case_d_repaired_dimension_is_never_selected_again():
    history = _history(
        (D, "meaning", False), (D, "pinyin", False), (D, "context", True),
        (P, "meaning", True), (P, "meaning", True),
    )

    state = _state(history)

    assert "meaning" not in state["practice"]["unresolvedDimensions"]
    assert state["practice"]["nextDimension"] == "pinyin"


def test_case_d_after_every_repair_no_dimension_is_forced_by_old_history():
    history = _history(
        (D, "meaning", False), (D, "pinyin", True), (D, "context", True),
        (P, "meaning", True), (P, "meaning", True),
    )

    state = _state(history)

    assert state["practice"]["unresolvedDimensions"] == []
    assert state["practice"]["selectionReason"] != "repair_unresolved"


# ---- Case E: high P(Learned) cannot override an unresolved dimension --------

def test_case_e_high_p_learned_with_unresolved_dimension_is_not_complete_or_strong():
    state = _state(_history((D, "meaning", False), (D, "pinyin", True), (D, "context", True)))

    assert state["bkt"]["pLearned"] > 0.95
    assert state["practice"]["unresolvedDimensions"] == ["meaning"]
    assert state["practice"]["status"] != "COMPLETE"
    assert state["review"]["status"] != "STRONG"


# ---- Case F: all repairs completed -----------------------------------------

def test_case_f_all_repairs_completed_is_strong_and_sm2_enrollable():
    from test_review_queue import _FakeDB, TODAY
    from analytics.learner_model.srs_store import enroll_strong_words

    history = _history(
        (D, "meaning", False), (D, "pinyin", False), (D, "context", True),
        (P, "meaning", True), (P, "meaning", True), (P, "pinyin", True), (P, "pinyin", True),
    )
    state = _state(history)

    assert state["diagnostic"]["coverageComplete"] is True
    assert state["practice"]["unresolvedDimensions"] == []
    assert state["practice"]["status"] == "COMPLETE"
    assert state["bkt"]["pLearned"] >= BKT_CONFIG.mastery_threshold
    assert state["review"] == {"status": "STRONG", "candidate": False}

    enrolled = enroll_strong_words(_FakeDB(rows=[]), "s1", [{"wordId": "W", "vocabularyState": state}], now=TODAY)
    assert enrolled == 1


# ---- Repair rule details ----------------------------------------------------

@pytest.mark.parametrize("dimension", ["meaning", "pinyin", "context"])
def test_a_failed_corrective_answer_resets_that_dimensions_progress(dimension):
    history = _history(
        *((D, observed, observed != dimension) for observed in ("meaning", "pinyin", "context")),
        (P, dimension, True), (P, dimension, False), (P, dimension, True),
    )

    state = _state(history)
    assert unresolved_dimensions(history) == [dimension]
    assert state["practice"]["repairProgress"] == {dimension: 1}
    assert state["practice"]["status"] == "IN_PROGRESS"
    assert state["review"]["status"] == "NEEDS_PRACTICE"


def test_corrective_success_in_another_dimension_never_repairs_a_failed_one():
    history = _history(
        (D, "pinyin", False), (D, "meaning", True), (D, "context", True),
        (P, "meaning", True), (P, "context", True), (P, "meaning", True), (P, "context", True),
    )

    assert unresolved_dimensions(history) == ["pinyin"]


def test_maintenance_failure_reopens_only_that_dimension():
    history = _history(
        (D, "meaning", True), (D, "pinyin", True), (D, "context", True),
        (M, "context", False),
    )

    state = _state(history)

    assert state["practice"]["unresolvedDimensions"] == ["context"]
    assert state["review"]["status"] == "NEEDS_PRACTICE"


def test_maintenance_or_diagnostic_success_does_not_repair_a_dimension():
    # Only corrective practice repairs; a later correct diagnostic/maintenance
    # observation is evidence for BKT but not a repair event.
    history = _history(
        (D, "meaning", False), (D, "pinyin", True), (D, "context", True),
        (M, "meaning", True), (D, "meaning", True),
    )

    assert unresolved_dimensions(history) == ["meaning"]


def test_unmapped_rows_are_ignored_by_the_corrective_state():
    history = _history((D, "meaning", True)) + [
        {"activity_type": D, "knowledge_dimension": None, "question_type": "unknown", "correct": False, "occurred_at": None},
    ]

    assert unresolved_dimensions(history) == []


# ---- Deterministic selection ------------------------------------------------

@pytest.mark.parametrize(
    ("unresolved", "covered", "observations", "expected"),
    [
        (["pinyin", "context"], ["meaning", "pinyin", "context"], 9, ("pinyin", "repair_unresolved")),
        ([], ["meaning", "context"], 4, ("pinyin", "complete_coverage")),
        ([], ["meaning", "pinyin", "context"], 3, ("meaning", "build_evidence")),
        ([], ["meaning", "pinyin", "context"], 4, ("pinyin", "build_evidence")),
        ([], ["meaning", "pinyin", "context"], 5, ("context", "build_evidence")),
    ],
)
def test_selection_is_deterministic_and_ordered(unresolved, covered, observations, expected):
    assert select_corrective_dimension(unresolved, covered, observations) == expected


# ---- Audit trace ------------------------------------------------------------

def test_trace_reconstructs_unresolved_dimensions_before_and_after_each_observation():
    history = _history(
        (D, "meaning", False), (D, "pinyin", True), (P, "meaning", True), (P, "meaning", True),
    )

    trace = corrective_trace(history)

    assert [step["unresolvedBefore"] for step in trace] == [[], ["meaning"], ["meaning"], ["meaning"]]
    assert [step["unresolvedAfter"] for step in trace] == [["meaning"], ["meaning"], ["meaning"], []]
    assert [step["dimension"] for step in trace] == ["meaning", "pinyin", "meaning", "meaning"]
    assert [step["activityType"] for step in trace] == [D, D, P, P]


def test_practice_state_carries_a_policy_version_for_auditability():
    state = _state(_history((D, "meaning", True), (D, "pinyin", True), (D, "context", True)))

    assert state["practice"]["policyVersion"]
    assert state["practice"]["requiredSuccesses"] == 2


# ---- Audit trace with BKT numbers ------------------------------------------

def test_observation_trace_keeps_p_learned_and_predicted_correctness_distinct():
    from analytics.learner_model.bkt.mastery import observation_trace

    history = _history((D, "meaning", True), (D, "pinyin", False), (P, "pinyin", True))

    steps = observation_trace(history, BKT_CONFIG, BKT_CONFIG.initial_mastery)

    # P(Learned) matches the production replay at every prefix (no new numerics).
    for index, step in enumerate(steps, start=1):
        expected = replay_bkt_typed(
            ((row["correct"], row["question_type"]) for row in history[:index]), BKT_CONFIG,
        )
        assert step["pLearned"] == pytest.approx(expected)
    assert steps[0]["pLearnedBefore"] == pytest.approx(BKT_CONFIG.initial_mastery)
    assert steps[1]["pLearnedBefore"] == pytest.approx(steps[0]["pLearned"])
    # Predicted correctness of the NEXT answer is P(L)*(1-slip) + (1-P(L))*guess,
    # which is NOT P(Learned): at p=.20 with MCQ rates it is .34, not .20.
    assert steps[0]["pCorrectBefore"] == pytest.approx(0.20 * 0.90 + 0.80 * 0.20)
    assert steps[0]["pCorrectBefore"] != pytest.approx(steps[0]["pLearnedBefore"])
    # The typed (pinyin) step uses the typed guess/slip pair.
    before = steps[1]["pLearnedBefore"]
    assert steps[1]["pCorrectBefore"] == pytest.approx(before * (1 - 0.15) + (1 - before) * 0.05)


def test_observation_trace_includes_corrective_and_provenance_fields():
    from analytics.learner_model.bkt.mastery import observation_trace

    history = _history((D, "meaning", False), (P, "meaning", True), (P, "meaning", True))

    steps = observation_trace(history, BKT_CONFIG, BKT_CONFIG.initial_mastery)

    assert [step["unresolvedAfter"] for step in steps] == [["meaning"], ["meaning"], []]
    assert steps[0]["unresolvedBefore"] == []
    assert {"itemId", "questionType", "dimension", "activityType", "occurredAt", "modelVersion", "policyVersion"} <= set(steps[0])


def test_trace_records_what_the_policy_would_have_selected_before_each_observation():
    history = _history(
        (D, "meaning", False), (D, "pinyin", False), (D, "context", True),
        (P, "meaning", True), (P, "meaning", True), (P, "pinyin", True),
    )

    trace = corrective_trace(history)

    # Before the corrective answers the policy targets meaning; once meaning is
    # repaired (after step 5) it targets pinyin. Step 6 therefore matches policy.
    assert [(step["nextDimensionBefore"], step["selectionReasonBefore"]) for step in trace[3:]] == [
        ("meaning", "repair_unresolved"),
        ("meaning", "repair_unresolved"),
        ("pinyin", "repair_unresolved"),
    ]
    assert trace[5]["dimension"] == trace[5]["nextDimensionBefore"]
    # Before any evidence exists the first uncovered dimension is the target.
    assert (trace[0]["nextDimensionBefore"], trace[0]["selectionReasonBefore"]) == ("meaning", "complete_coverage")
