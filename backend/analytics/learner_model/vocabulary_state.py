"""Normalized, server-derived vocabulary state.

This module deliberately contains presentation state, not a second learner
model.  There is one BKT probability per word; the response ledger supplies
the dimension evidence and corrective-practice history that explain it.

Two different questions are answered separately, and BOTH gate ``STRONG``:

* BKT, ``P(Learned)``: "how strong is the total, pooled evidence that the
  learner knows this word?"  One probability per word, never per dimension.
* Corrective state, ``unresolvedDimensions``: "is there a required dimension
  (meaning / pinyin / context) with a demonstrated failure that has not yet
  been repaired?"  It is derived from the ledger, not folded into P(Learned).

``STRONG`` is a *system classification*, not a claim that the learner
definitely knows the word.  A word is STRONG only when all of these hold:

    diagnostic coverage complete   (lesson rounds done AND every dimension observed)
    AND observation_count >= minimum_observations
    AND unresolvedDimensions is empty
    AND P(Learned) >= mastery_threshold

``unresolvedDimensions`` is the single source of truth for "what to repair
next".  The frontend question selector reads ``practice.nextDimension`` from
here rather than recomputing anything from historical failures.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Iterator

from analytics.learner_model.srs import SrsState, is_due


DIMENSION_KEYS = ("meaning", "pinyin", "context")

# Version of the corrective rules in this module (not the BKT model version).
CORRECTIVE_POLICY_VERSION = "per-dimension-repair-v1"

# The one repair rule: a dimension is repaired by this many CONSECUTIVE correct
# corrective-practice answers in that same dimension.  Any later incorrect
# answer in that dimension (diagnostic, practice or maintenance) reopens it
# with progress reset to zero.  Correct answers in other dimensions never count.
REPAIR_SUCCESSES_PER_DIMENSION = 2

CORRECTIVE_ACTIVITY = "personalized_practice"
# A failed response in one of these activities marks its dimension unresolved.
# Scheduled maintenance is not corrective practice, but a failure there still
# shows the learner which dimension needs repair.
FAILURE_ACTIVITIES = frozenset({"diagnostic", "scheduled_maintenance", CORRECTIVE_ACTIVITY})


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


def _ordered(dimensions: Iterable[str]) -> list[str]:
    """Stable ``meaning -> pinyin -> context`` order; unknown keys are dropped."""
    present = set(dimensions)
    return [key for key in DIMENSION_KEYS if key in present]


def _replay_corrective(history: Iterable[dict[str, Any]]) -> Iterator[tuple[dict[str, Any], str | None, dict[str, int], dict[str, int]]]:
    """Walk the ledger once, tracking repair progress per unresolved dimension.

    Yields ``(row, dimension, progress_before, progress_after)`` where progress
    maps each currently unresolved dimension to its consecutive corrective
    successes so far.  This is the only place the repair rule is implemented.
    """
    progress: dict[str, int] = {}
    for row in history:
        before = dict(progress)
        dimension = dimension_key(row)
        activity = row.get("activity_type")
        if dimension is not None and activity in FAILURE_ACTIVITIES:
            if not bool(row.get("correct")):
                progress[dimension] = 0
            elif activity == CORRECTIVE_ACTIVITY and dimension in progress:
                progress[dimension] += 1
                if progress[dimension] >= REPAIR_SUCCESSES_PER_DIMENSION:
                    del progress[dimension]
        yield row, dimension, before, dict(progress)


def failed_dimensions(history: Iterable[dict[str, Any]]) -> set[str]:
    """Dimensions with at least one failed response, repaired or not (audit only;
    never a selection input -- use ``unresolved_dimensions`` for that)."""
    return {
        dimension
        for row in history
        if (dimension := dimension_key(row)) is not None
        and row.get("activity_type") in FAILURE_ACTIVITIES
        and not bool(row.get("correct"))
    }


def unresolved_dimensions(history: Iterable[dict[str, Any]]) -> list[str]:
    """Dimensions whose latest failure has not yet been repaired, in stable order."""
    final: dict[str, int] = {}
    for _row, _dimension, _before, final in _replay_corrective(history):
        pass
    return _ordered(final)


def corrective_trace(history: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-observation audit trail of the corrective state (reconstructable
    from the ledger; nothing here is stored separately).

    ``nextDimensionBefore`` / ``selectionReasonBefore`` are what the policy
    would have selected immediately before the observation, so a reviewer can
    compare them with the dimension that was actually practiced.
    """
    steps: list[dict[str, Any]] = []
    covered: set[str] = set()
    for index, (row, dimension, before, after) in enumerate(_replay_corrective(history), start=1):
        next_dimension, reason = select_corrective_dimension(before, covered, index - 1)
        steps.append({
            "index": index,
            "itemId": row.get("item_id"),
            "questionType": row.get("question_type"),
            "dimension": dimension,
            "activityType": row.get("activity_type"),
            "correct": bool(row.get("correct")),
            "occurredAt": row.get("occurred_at"),
            "unresolvedBefore": _ordered(before),
            "unresolvedAfter": _ordered(after),
            "nextDimensionBefore": next_dimension,
            "selectionReasonBefore": reason,
        })
        if dimension is not None:
            covered.add(dimension)
    return steps


def covered_dimensions(history: Iterable[dict[str, Any]]) -> list[str]:
    """Dimensions with at least one observation of any activity type."""
    return _ordered({key for key in (dimension_key(row) for row in history) if key})


def select_corrective_dimension(
    unresolved: Iterable[str], covered: Iterable[str], observation_count: int,
) -> tuple[str, str]:
    """Deterministically choose the next practice dimension and say why.

    1. ``repair_unresolved``: the first unresolved dimension (stable order).
    2. ``complete_coverage``: the first dimension never observed for this word.
    3. ``build_evidence``: nothing to repair and full coverage, but BKT is
       still below threshold; rotate by observation count (no randomness).
    """
    pending = _ordered(unresolved)
    if pending:
        return pending[0], "repair_unresolved"
    uncovered = [key for key in DIMENSION_KEYS if key not in set(covered)]
    if uncovered:
        return uncovered[0], "complete_coverage"
    return DIMENSION_KEYS[max(0, observation_count) % len(DIMENSION_KEYS)], "build_evidence"


def build_practice_state(
    history: list[dict[str, Any]],
    *,
    required: bool,
) -> dict[str, Any]:
    """Return the explicit corrective-practice state derived from the ledger.

    ``unresolvedDimensions`` is authoritative.  ``COMPLETE`` means every
    dimension that ever failed has been repaired under the single repair rule
    (``REPAIR_SUCCESSES_PER_DIMENSION``); it does not by itself imply STRONG.
    """
    progress: dict[str, int] = {}
    for _row, _dimension, _before, progress in _replay_corrective(history):
        pass
    unresolved = _ordered(progress)
    ever_failed = failed_dimensions(history)
    has_practice = any(row.get("activity_type") == CORRECTIVE_ACTIVITY for row in history)
    if not required:
        status = "NOT_REQUIRED"
    elif not unresolved and ever_failed:
        status = "COMPLETE"
    elif has_practice:
        status = "IN_PROGRESS"
    else:
        status = "PENDING"
    return {
        "status": status,
        "unresolvedDimensions": unresolved,
        "repairedDimensions": _ordered(ever_failed - set(unresolved)),
        "repairProgress": {key: progress[key] for key in unresolved},
        "requiredSuccesses": REPAIR_SUCCESSES_PER_DIMENSION,
        "policyVersion": CORRECTIVE_POLICY_VERSION,
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
    unresolved = unresolved_dimensions(history)
    covered = covered_dimensions(history)
    # "Diagnostic coverage complete" is lesson-level (all three rounds run) AND
    # word-level (every dimension actually observed for this word), so a high
    # P(Learned) built from one dimension can never classify a word STRONG.
    coverage_complete = diagnostic_complete and len(covered) == len(DIMENSION_KEYS)
    # The mastery gate. STRONG is a system classification, not certainty that
    # the learner knows the word: BKT strength AND no unrepaired dimension.
    is_strong = (
        coverage_complete
        and observation_count >= minimum_observations
        and not unresolved
        and p_learned >= mastery_threshold
    )
    if is_strong:
        review_status = "STRONG"
    elif observation_count == 0:
        # A placement prior is an initialization estimate, not learner
        # evidence. Keep an unseen word semantically unassessed even after
        # the diagnostic gate is open.
        review_status = "NOT_ASSESSED"
    elif diagnostic_complete:
        review_status = "NEEDS_PRACTICE"
    elif history:
        review_status = "PROVISIONAL_REVIEW"
    else:
        review_status = "NOT_ASSESSED"

    practice_required = bool(failed_dimensions(history)) or p_learned < mastery_threshold or review_status == "NEEDS_PRACTICE"
    practice = build_practice_state(history, required=practice_required)
    next_dimension, selection_reason = (
        (None, None) if is_strong else select_corrective_dimension(unresolved, covered, observation_count)
    )
    practice["nextDimension"] = next_dimension
    practice["selectionReason"] = selection_reason

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
            "coveredDimensions": covered,
            "coverageComplete": coverage_complete,
        },
        "review": {
            "status": review_status,
            "candidate": diagnostic_complete and review_status == "NEEDS_PRACTICE",
        },
        "practice": practice,
        "scheduling": _schedule_state(srs_state, now),
    }
