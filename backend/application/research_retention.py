"""Use-case orchestration for the Epic 5 adaptive SM-2 + yoked retention
feature.

Reuses analytics/srs.py's SM-2 math unchanged (review/is_due/should_advance/
quality_from_response) - this module only adds enrollment-on-core-completion
(Task 5.3) and the yoke-mirroring step (Task 5.6) that production's
scheduler has no concept of. Persists to vocab_research_retention_state/
_events, never to production's student_vocab_srs (Task 5.1).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from analytics.srs import (
    DAY_SECONDS,
    SRS_ALGORITHM_VERSION,
    SrsState,
    is_due,
    quality_from_response,
    review,
    should_advance,
)
from domain.vocabulary.research_retention import initial_enrollment_state, mirror_yoked_state
from repositories import vocabulary_research as repo


class ResearchReviewUnavailableError(Exception):
    """The student is not an active research participant right now."""


def _row_to_srs_state(row: dict[str, Any]) -> SrsState:
    def as_datetime(value: Any) -> datetime | None:
        if value is None:
            return None
        return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))

    return SrsState(
        reps=int(row["reps"]),
        ease=float(row["ease"]),
        interval_days=int(row["interval_days"]),
        due_on=as_datetime(row["due_on"]),
        last_reviewed_on=as_datetime(row["last_reviewed_on"]),
    )


def _word_id_of(result: dict[str, Any]) -> str | None:
    value = result.get("conceptId") or result.get("word")
    return str(value) if value else None


def enroll_section_retention(
    db, student_id: str, study_id: str, section_id: str, *, now: datetime | None = None, day_seconds: float = DAY_SECONDS,
) -> int:
    """Task 5.3: once a research participant's core rounds for one section
    are complete, every word assigned to them in that section enters the
    retention pipeline - adaptive and yoked alike, and regardless of BKT
    status (a mastery-blind condition's words have no BKT status at all).
    Idempotent: a word already enrolled (from a prior call) is left alone.
    """
    now = now or datetime.now(timezone.utc)
    assignments = [row for row in repo.find_assignments_for_student(db, study_id, student_id) if row["section_id"] == section_id]
    if not assignments:
        return 0
    word_ids = [row["word_id"] for row in assignments]
    existing = repo.find_retention_states(db, student_id, study_id, word_ids)
    enrolled = 0
    for row in assignments:
        word_id = row["word_id"]
        if word_id in existing:
            continue
        state = initial_enrollment_state(now, day_seconds)
        accepted = repo.record_retention_event(
            db, student_id=student_id, study_id=study_id, word_id=word_id,
            event_type="enrollment", old_state=SrsState(), new_state=state,
            source_response_id=f"enrollment:{word_id}", algorithm_version=SRS_ALGORITHM_VERSION,
            occurred_at=now,
        )
        if not accepted:
            continue
        repo.upsert_retention_state(
            db, student_id=student_id, study_id=study_id, word_id=word_id,
            state=state, algorithm_version=SRS_ALGORITHM_VERSION, now=now.isoformat(),
        )
        enrolled += 1
    return enrolled


def apply_retention_review(
    db, student_id: str, study_id: str, question_results: Iterable[dict[str, Any]],
    *, now: datetime | None = None, day_seconds: float = DAY_SECONDS,
) -> int:
    """Task 5.4/5.6: grade a research review session.

    An adaptive_sm2 word is graded with the real SM-2 review() - identical
    math to production. A yoked word is never graded here: its own answer is
    logged as an audit-only "yoked_exposure" event and its schedule is left
    untouched; only mirror_yoked_state(), triggered by its PAIRED adaptive
    word's own review, may change it. Returns how many words' schedules
    actually advanced (adaptive grades + yoked mirrors).
    """
    now = now or datetime.now(timezone.utc)
    assignments = repo.find_assignments_for_student(db, study_id, student_id)
    policy_by_word = {row["word_id"]: row["retention_policy"] for row in assignments}

    last_by_word: dict[str, dict[str, Any]] = {}
    for result in question_results:
        if result.get("authoritativeResolved") is not True:
            continue
        if result.get("activityType") in {"personalized_practice", "practice"}:
            continue
        word_id = _word_id_of(result)
        if word_id is not None and isinstance(result.get("correct"), bool):
            last_by_word[word_id] = result
    if not last_by_word:
        return 0

    states = {
        word_id: _row_to_srs_state(row)
        for word_id, row in repo.find_retention_states(db, student_id, study_id, list(last_by_word)).items()
    }
    updated = 0
    for word_id, result in last_by_word.items():
        state = states.get(word_id)
        if state is None:
            # Not enrolled - a legitimately due review session word always
            # is, but an unenrolled/unknown word must not silently create one.
            continue
        source_response_id = (
            str(result.get("sourceResponseId") or result.get("responseId") or result.get("quizId"))
            if (result.get("sourceResponseId") or result.get("responseId") or result.get("quizId"))
            else None
        )
        if not source_response_id:
            continue

        if policy_by_word.get(word_id) == "yoked":
            repo.record_retention_event(
                db, student_id=student_id, study_id=study_id, word_id=word_id,
                event_type="yoked_exposure", old_state=state, new_state=state,
                source_response_id=source_response_id, algorithm_version=SRS_ALGORITHM_VERSION,
                correct=bool(result["correct"]), occurred_at=now,
            )
            continue

        if not is_due(state, now) or not should_advance(state, now, day_seconds=day_seconds):
            continue
        q = quality_from_response(bool(result["correct"]))
        next_state = review(state, q, now, day_seconds=day_seconds)
        accepted = repo.record_retention_event(
            db, student_id=student_id, study_id=study_id, word_id=word_id,
            event_type="maintenance_success" if result["correct"] else "maintenance_failure",
            old_state=state, new_state=next_state, source_response_id=source_response_id,
            algorithm_version=SRS_ALGORITHM_VERSION, quiz_id=str(result["quizId"]) if result.get("quizId") else None,
            attempt_id=str(result["attemptId"]) if result.get("attemptId") else None,
            correct=bool(result["correct"]), quality=q, occurred_at=now,
        )
        if not accepted:
            continue
        repo.upsert_retention_state(
            db, student_id=student_id, study_id=study_id, word_id=word_id,
            state=next_state, algorithm_version=SRS_ALGORITHM_VERSION, now=now.isoformat(),
        )
        states[word_id] = next_state
        updated += 1

        for dependent_id in repo.find_yoked_dependents(db, study_id, student_id, word_id):
            dependent_state = states.get(dependent_id)
            if dependent_state is None:
                dependent_row = repo.find_retention_states(db, student_id, study_id, [dependent_id]).get(dependent_id)
                if dependent_row is None:
                    continue
                dependent_state = _row_to_srs_state(dependent_row)
            mirrored = mirror_yoked_state(next_state)
            mirror_accepted = repo.record_retention_event(
                db, student_id=student_id, study_id=study_id, word_id=dependent_id,
                event_type="yoked_mirror", old_state=dependent_state, new_state=mirrored,
                source_response_id=f"{source_response_id}:mirror:{dependent_id}",
                algorithm_version=SRS_ALGORITHM_VERSION, occurred_at=now,
            )
            if not mirror_accepted:
                continue
            repo.upsert_retention_state(
                db, student_id=student_id, study_id=study_id, word_id=dependent_id,
                state=mirrored, algorithm_version=SRS_ALGORITHM_VERSION, now=now.isoformat(),
            )
            states[dependent_id] = mirrored
            updated += 1
    return updated


def build_review_session(db, student_id: str) -> dict:
    """Task 5.7: which words are due right now for this research
    participant, from vocab_research_retention_state only - never production's
    SM-2 queue. A yoked word's due-ness is whatever its last mirror set it to."""
    from application.vocabulary_research import get_research_context

    context = get_research_context(db, student_id)
    if not context.active or not context.study_id:
        raise ResearchReviewUnavailableError("Student is not an active research participant.")
    now = datetime.now(timezone.utc)
    states = repo.find_retention_states(db, student_id, context.study_id)
    due_word_ids = sorted(word_id for word_id, row in states.items() if is_due(_row_to_srs_state(row), now))
    return {"studyId": context.study_id, "wordIds": due_word_ids}
