"""STEP 8: local synthetic/fake pilot sequence + reconstruction proof.

    python -m assistive_feedback.pilot_dry_run

Builds three synthetic scenarios directly against `research_log` (no real
audio, no F1/E2 inference -- this proves the LOGGING SCHEMA and
RECONSTRUCTION are correct, independent of model behavior, exactly what
STEP 8 asks for) into a dedicated dry-run log file (never the production
log path), then reconstructs each sequence using ONLY explicit fields
(`participant_id`, `session_id`, `item_id`, `attempt_id`,
`retry_of_attempt_id`, `attempt_number`, `attempt_type`) -- `timestamp` is
never read by any reconstruction/verification step here.

Scenario 1 (P001 / S001 / ITEM001): the full flow STEP 8 lists --
initial whole-sentence attempt -> CHECK_THIS_TONE on one syllable ->
learner chooses a focused retry -> focused retry recorded (resolves to
ACCEPT) -> optional final whole-sentence attempt -> progression.

Scenario 2 (P002 / S001 / ITEM002): NO_ISSUE_DETECTED with no retry offered.

Scenario 3 (P003 / S001 / ITEM003): NO_AUTOMATIC_JUDGMENT, progresses anyway.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from assistive_feedback import research_log as rl

DRY_RUN_LOG_PATH = Path("private-data/assistive_feedback_dry_run_log.jsonl")


def _syllable(
    attempt_id: str, participant_id: str, item_id: str, session_id: str,
    syllable_index: int, character: str, policy_state: str,
    attempt_number: int, attempt_type: rl.AttemptType,
    retry_of_attempt_id: str | None = None,
    retry_of_syllable_index: int | None = None,
    progression_outcome: rl.ProgressionOutcome = "continued_immediately",
) -> rl.AttemptLogRecord:
    return rl.AttemptLogRecord(
        attempt_id=attempt_id, participant_id=participant_id, item_id=item_id,
        syllable_index=syllable_index, character=character, policy_state=policy_state,
        f1_risk_score=0.1 if policy_state == "NEEDS_PRACTICE" else 0.9,
        e2_diagnostic_category="T1", e2_score=10.0 if policy_state == "NEEDS_PRACTICE" else 90.0,
        expected_tone=1, accepted_surface_tones=[1],
        session_id=session_id, attempt_number=attempt_number, attempt_type=attempt_type,
        retry_of_attempt_id=retry_of_attempt_id, retry_of_syllable_index=retry_of_syllable_index,
        progression_outcome=progression_outcome,
        study_phase="pilot", feedback_enabled=True,
    )


def build_scenario_1() -> list[rl.AttemptLogRecord]:
    """P001 / S001 / ITEM001: initial -> CHECK_THIS_TONE -> focused retry
    (chosen) -> resolves ACCEPT -> optional final whole-sentence attempt ->
    progression."""
    participant, session, item = "P001", "S001", "ITEM001"
    records = [
        # 1. Initial whole-sentence attempt: syllable 0 flagged, syllable 1 fine.
        _syllable("A1", participant, item, session, 0, "他", "NEEDS_PRACTICE", 1, "WHOLE_SENTENCE_INITIAL"),
        _syllable("A1", participant, item, session, 1, "好", "ACCEPT", 1, "WHOLE_SENTENCE_INITIAL"),
        # 2. (CHECK_THIS_TONE feedback is the state above, shown to the
        #    learner -- not a separate log event.)
        # 3/4. Learner chooses the focused retry; it is recorded as its own
        #    attempt, linked back via retry_of_attempt_id (never a guess
        #    from timing) -- resolves to ACCEPT this time.
        _syllable("A2", participant, item, session, 0, "他", "ACCEPT", 2, "FOCUSED_RETRY",
                  retry_of_attempt_id="A1", retry_of_syllable_index=0),
        # 5. Optional final whole-sentence attempt, both syllables now fine.
        _syllable("A3", participant, item, session, 0, "他", "ACCEPT", 3, "WHOLE_SENTENCE_FINAL",
                  progression_outcome="continued_after_retry"),
        _syllable("A3", participant, item, session, 1, "好", "ACCEPT", 3, "WHOLE_SENTENCE_FINAL",
                  progression_outcome="continued_after_retry"),
    ]
    return records


def build_scenario_2() -> list[rl.AttemptLogRecord]:
    """P002 / S001 / ITEM002: NO_ISSUE_DETECTED, no retry offered or taken."""
    return [
        _syllable("B1", "P002", "ITEM002", "S001", 0, "媽", "ACCEPT", 1, "WHOLE_SENTENCE_INITIAL"),
        _syllable("B1", "P002", "ITEM002", "S001", 1, "麻", "ACCEPT", 1, "WHOLE_SENTENCE_INITIAL"),
    ]


def build_scenario_3() -> list[rl.AttemptLogRecord]:
    """P003 / S001 / ITEM003: NO_AUTOMATIC_JUDGMENT, progresses anyway
    (never blocked -- STEP 3's invariant)."""
    return [
        _syllable("C1", "P003", "ITEM003", "S001", 0, "馬", "UNCERTAIN", 1, "WHOLE_SENTENCE_INITIAL"),
    ]


def run(path: Path = DRY_RUN_LOG_PATH) -> dict[str, Any]:
    if path.exists():
        path.unlink()  # fresh dry run every time -- this file is scratch, not the real log

    all_records = build_scenario_1() + build_scenario_2() + build_scenario_3()
    rl.log_attempt_batch(all_records, path=path)

    logged = rl.read_records(path)

    sequence_1 = rl.reconstruct_sequence(logged, "P001", "ITEM001", session_id="S001")
    sequence_2 = rl.reconstruct_sequence(logged, "P002", "ITEM002", session_id="S001")
    sequence_3 = rl.reconstruct_sequence(logged, "P003", "ITEM003", session_id="S001")

    verification = {
        "n_logged": len(logged),
        "scenario_1": {
            "n_attempts": len(sequence_1),
            "attempt_types_in_order": [a["attempt_type"] for a in sequence_1],
            "attempt_1_syllable_0_state": sequence_1[0]["syllables"][0]["policy_state"],
            "attempt_1_syllable_0_retry_chosen": sequence_1[0]["syllables"][0]["retry_chosen"],
            "attempt_1_syllable_0_second_attempt_state": sequence_1[0]["syllables"][0]["second_attempt_policy_state"],
            "attempt_2_is_focused_retry_of_attempt_1": sequence_1[1]["retry_of_attempt_id"] == "A1",
            "attempt_2_resolved_state": sequence_1[1]["syllables"][0]["policy_state"],
            "final_progression_outcome": sequence_1[2]["syllables"][0]["progression_outcome"],
        },
        "scenario_2_no_issue_no_retry": {
            "n_attempts": len(sequence_2),
            "all_accept": all(s["policy_state"] == "ACCEPT" for a in sequence_2 for s in a["syllables"]),
            "retry_offered": any(s["policy_state"] == "NEEDS_PRACTICE" for a in sequence_2 for s in a["syllables"]),
        },
        "scenario_3_uncertain_progresses": {
            "n_attempts": len(sequence_3),
            "state": sequence_3[0]["syllables"][0]["policy_state"],
            "progression_outcome": sequence_3[0]["syllables"][0]["progression_outcome"],
            "progressed_without_needs_practice_ever_appearing": not any(
                s["policy_state"] == "NEEDS_PRACTICE" for a in sequence_3 for s in a["syllables"]
            ),
        },
        "metrics": {
            "retry_rate": rl.retry_rate(logged),
            "flagged_syllable_count": rl.flagged_syllable_count(logged),
            "uncertain_case_count": rl.uncertain_case_count(logged),
            "completion_rate": rl.completion_rate(logged),
            "attempt1_to_attempt2_transitions": {
                f"{k[0]}->{k[1]}": v for k, v in rl.attempt1_to_attempt2_transition_counts(logged).items()
            },
        },
    }

    # Assertions, not just printouts -- this IS the verification, not a demo.
    assert verification["scenario_1"]["n_attempts"] == 3
    assert verification["scenario_1"]["attempt_types_in_order"] == [
        "WHOLE_SENTENCE_INITIAL", "FOCUSED_RETRY", "WHOLE_SENTENCE_FINAL",
    ]
    assert verification["scenario_1"]["attempt_1_syllable_0_state"] == "NEEDS_PRACTICE"
    assert verification["scenario_1"]["attempt_1_syllable_0_retry_chosen"] is True
    assert verification["scenario_1"]["attempt_1_syllable_0_second_attempt_state"] == "ACCEPT"
    assert verification["scenario_1"]["attempt_2_is_focused_retry_of_attempt_1"] is True
    assert verification["scenario_1"]["attempt_2_resolved_state"] == "ACCEPT"
    assert verification["scenario_1"]["final_progression_outcome"] == "continued_after_retry"
    assert verification["scenario_2_no_issue_no_retry"]["all_accept"] is True
    assert verification["scenario_2_no_issue_no_retry"]["retry_offered"] is False
    assert verification["scenario_3_uncertain_progresses"]["state"] == "UNCERTAIN"
    assert verification["scenario_3_uncertain_progresses"]["progression_outcome"] == "continued_immediately"
    assert verification["scenario_3_uncertain_progresses"]["progressed_without_needs_practice_ever_appearing"] is True

    return verification


if __name__ == "__main__":
    import json

    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("\nAll STEP 8 assertions passed -- reconstruction verified without using timestamps heuristically.")
