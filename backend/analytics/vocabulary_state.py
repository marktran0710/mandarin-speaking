"""Normalized, server-derived vocabulary state.

This module deliberately contains presentation state, not a second learner
model.  There is one BKT probability per word; the response ledger supplies
the dimension evidence and corrective-practice history that explain it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from analytics.srs import SrsState, is_due


DIMENSION_KEYS = ("meaning", "pinyin", "context")
PRACTICE_SUCCESS_TARGET = 2


def dimension_key(row: dict[str, Any]) -> str | None:
    """Map authoritative assessment facts to the learner-facing dimensions."""
    value = str(row.get("knowledge_dimension") or "").strip().casefold()
    if value in {"meaning", "basic_meaning", "semantic"}:
        return "meaning"
    if value in {"pinyin", "pinyin_production", "pronunciation"}:
        return "pinyin"
    if value in {"context", "contextual_recall", "contextual_productive_recall"}:
        return "context"

    question_type = str(row.get("question_type") or "").strip().casefold()
    if question_type in {"basic_meaning_mcq", "translation", "reverse", "meaning_mcq"}:
        return "meaning"
    if question_type in {"character_to_pinyin_typing", "pinyin", "pinyin_production"}:
        return "pinyin"
    if question_type in {"context_cloze_mcq", "contextual_productive_recall", "productive_recall", "context"}:
        return "context"
    return None


def _empty_dimension_evidence() -> dict[str, Any]:
    return {"total": 0, "correct": 0, "incorrect": 0, "lastResponseAt": None}


def build_evidence(history: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate immutable response facts without changing BKT replay."""
    by_dimension = {key: _empty_dimension_evidence() for key in DIMENSION_KEYS}
    total = correct = 0
    last_response_at: Any = None
    for row in history:
        is_correct = bool(row.get("correct"))
        total += 1
        correct += int(is_correct)
        last_response_at = row.get("occurred_at")
        key = dimension_key(row)
        if key is None:
            continue
        dimension = by_dimension[key]
        dimension["total"] += 1
        dimension["correct"] += int(is_correct)
        dimension["incorrect"] += int(not is_correct)
        dimension["lastResponseAt"] = row.get("occurred_at")
    return {
        "total": total,
        "correct": correct,
        "incorrect": total - correct,
        "lastResponseAt": last_response_at,
        "byDimension": by_dimension,
    }


def build_practice_state(
    history: Iterable[dict[str, Any]],
    failed_dimensions: Iterable[str],
    *,
    required: bool,
) -> dict[str, Any]:
    """Return the explicit corrective-practice completion state.

    A corrective failure reopens the current requirement.  Successes before
    that failure are not reused, which keeps a learner from being marked
    complete after a later failed correction.  Dimension evidence is always
    server-derived; unknown dimensions cannot accidentally satisfy targeting.
    """
    failed = sorted({key for key in failed_dimensions if key in DIMENSION_KEYS})
    practice_rows = [row for row in history if row.get("activity_type") == "personalized_practice"]
    remediation_activities = {"diagnostic", "scheduled_maintenance", "personalized_practice"}
    # A later diagnostic or scheduled-maintenance failure starts a new
    # corrective epoch too. Looking only at personalized-practice failures
    # would leave a previously COMPLETE practice state visible after a failed
    # maintenance review.
    last_failure_index = max(
        (
            index
            for index, row in enumerate(history)
            if row.get("activity_type") in remediation_activities and not bool(row.get("correct"))
        ),
        default=-1,
    )
    current_rows = [
        row for row in history[last_failure_index + 1:]
        if row.get("activity_type") == "personalized_practice"
    ]
    if last_failure_index >= 0:
        latest_failed_dimension = dimension_key(history[last_failure_index])
        failed = [latest_failed_dimension] if latest_failed_dimension else []
    successful_rows = [row for row in current_rows if bool(row.get("correct"))]
    successful_dimensions = sorted({key for key in (dimension_key(row) for row in successful_rows) if key})
    targeted_success = bool(set(successful_dimensions).intersection(failed))
    successes = len(successful_rows)
    complete = successes >= PRACTICE_SUCCESS_TARGET and targeted_success and bool(failed)
    if not required:
        status = "NOT_REQUIRED"
    elif complete:
        status = "COMPLETE"
    elif practice_rows:
        status = "IN_PROGRESS"
    elif required:
        status = "PENDING"
    else:
        status = "NOT_REQUIRED"
    return {
        "status": status,
        "correctiveSuccesses": successes,
        "requiredSuccesses": PRACTICE_SUCCESS_TARGET,
        "failedDimensions": failed,
        "successfulDimensions": successful_dimensions,
        "targetedSuccess": targeted_success,
    }


def _schedule_state(srs_state: SrsState | None, now: datetime) -> dict[str, Any]:
    if srs_state is None:
        return {
            "status": "NOT_SCHEDULED",
            "reps": 0,
            "ease": None,
            "intervalDays": 0,
            "dueOn": None,
            "lastReviewedOn": None,
        }
    return {
        "status": "DUE_FOR_REVIEW" if is_due(srs_state, now) else "SCHEDULED",
        "reps": srs_state.reps,
        "ease": srs_state.ease,
        "intervalDays": srs_state.interval_days,
        "dueOn": srs_state.due_on.isoformat() if srs_state.due_on else None,
        "lastReviewedOn": srs_state.last_reviewed_on.isoformat() if srs_state.last_reviewed_on else None,
    }


def build_vocabulary_state(
    *,
    history: list[dict[str, Any]],
    p_learned: float,
    observation_count: int,
    diagnostic_complete: bool,
    mastery_threshold: float,
    minimum_observations: int,
    model_version: str,
    parameter_fingerprint: str,
    srs_state: SrsState | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    evidence = build_evidence(history)
    failed_dimensions: set[str] = set()
    # Any incorrect response that opens or reopens remediation is a valid
    # target for the next corrective practice. Maintenance failures matter
    # here too: scheduled review is separate from corrective practice, but it
    # still supplies the dimension the learner needs to repair.
    remediation_activities = {"diagnostic", "scheduled_maintenance", "personalized_practice"}
    for row in history:
        if row.get("activity_type") not in remediation_activities:
            continue
        key = dimension_key(row)
        if key and not bool(row.get("correct")):
            failed_dimensions.add(key)
    failed_dimensions_list = sorted(failed_dimensions)
    practice_required = bool(failed_dimensions) or p_learned < mastery_threshold
    practice = build_practice_state(history, failed_dimensions_list, required=practice_required)
    if practice["status"] == "COMPLETE" and p_learned >= mastery_threshold:
        review_status = "STRONG"
    elif diagnostic_complete and (p_learned < mastery_threshold or practice["status"] in {"PENDING", "IN_PROGRESS"}):
        review_status = "NEEDS_PRACTICE"
    elif diagnostic_complete and observation_count >= 1:
        review_status = "STRONG" if p_learned >= mastery_threshold else "NEEDS_PRACTICE"
    elif history:
        review_status = "PROVISIONAL_REVIEW"
    else:
        review_status = "NOT_ASSESSED"

    bkt_status = (
        "UNASSESSED" if observation_count < minimum_observations
        else "STRONG" if p_learned >= mastery_threshold
        else "DEVELOPING"
    )
    now = now or datetime.now(timezone.utc)
    return {
        "evidence": evidence,
        "bkt": {
            "pLearned": p_learned,
            "status": bkt_status,
            "modelVersion": model_version,
            "parameterFingerprint": parameter_fingerprint,
        },
        "diagnostic": {
            "status": "COMPLETE" if diagnostic_complete else "INCOMPLETE",
            "completed": diagnostic_complete,
        },
        "review": {
            "status": review_status,
            "candidate": diagnostic_complete and review_status == "NEEDS_PRACTICE",
        },
        "practice": practice,
        "scheduling": _schedule_state(srs_state, now),
    }
