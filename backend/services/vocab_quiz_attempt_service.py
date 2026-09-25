"""Use-case orchestration for recording and listing vocab quiz attempts.

Coordinates the quiz-attempt repository with BKT mastery updates and SRS
scheduling. Raises domain exceptions (not HTTPException) - the router maps
them to HTTP status codes, per the route/service boundary in
BACKEND_ARCHITECTURE_PLAN.md.
"""
import logging
from typing import Optional
from uuid import uuid4

from analytics.bkt_assessment_resolver import resolve_assessment_response
from analytics.bkt_mastery import get_vocabulary_mastery, record_attempt_and_rebuild
from analytics.srs_store import apply_srs_updates, enroll_strong_words
from application.vocabulary_research import (
    apply_response_routing,
    enroll_research_probes_for_attempt,
    enroll_research_retention_for_attempt,
    get_research_context,
    log_core_completion_event,
)
from api.schemas.models import VocabQuizAttemptRequest
from repositories import quiz_attempt_repository as repo

logger = logging.getLogger("speaking_app")


class AttemptConflictError(Exception):
    """A vocab quiz attempt payload conflicts with an existing stored attempt."""


def list_attempts(
    db,
    *,
    story_id: Optional[str] = None,
    student_name: Optional[str] = None,
    student_id: Optional[str] = None,
    include_results: bool = True,
) -> list[dict]:
    return repo.list_attempts(
        db,
        story_id=story_id,
        student_name=student_name,
        student_id=student_id,
        include_results=include_results,
    )


def _validated_question_results(db, attempt: VocabQuizAttemptRequest) -> list[dict]:
    """Resolve answers to published assessment facts before BKT sees them."""
    question_results = []
    for result in attempt.questionResults:
        payload = result.model_dump(exclude_none=True, exclude_defaults=True)
        resolved = resolve_assessment_response(db, attempt, payload)
        if not resolved.get("authoritativeResolved"):
            logger.warning(
                "BKT_UPDATE_SKIPPED question_id=%s reason=UNRESOLVED_ASSESSMENT_SOURCE",
                payload.get("itemId") or payload.get("word") or "unknown",
            )
        question_results.append(resolved)
    return question_results


def _srs_event_results(attempt: VocabQuizAttemptRequest, question_results: list[dict]) -> list[dict]:
    """Attach stable source identities so repeated API persistence is idempotent."""
    return [
        {
            **result,
            # Partial-save and completed-attempt requests can legitimately use
            # different transport ids. The quiz id carried on each answer is
            # the stable learner-response identity; include its question slot
            # so two answers for one word in a round remain distinct.
            "sourceResponseId": f"{result.get('quizId') or attempt.id}:{index}",
            "attemptId": attempt.id,
            "quizId": result.get("quizId") or attempt.id,
        }
        for index, result in enumerate(question_results)
    ]


def _enroll_newly_strong_words(db, student_id: str, attempt: VocabQuizAttemptRequest, now, day_seconds: float) -> None:
    """Start SRS only after the server marks a current-lesson word STRONG."""
    story_id = attempt.baseStoryId or attempt.storyId
    enroll_strong_words(
        db,
        student_id,
        get_vocabulary_mastery(db, student_id, story_id=story_id),
        now=now,
        day_seconds=day_seconds,
    )


def record_attempt(
    db,
    attempt: VocabQuizAttemptRequest,
    identity_id: str,
    *,
    now,
    day_seconds: float,
) -> list[dict]:
    """Persist a completed attempt, update BKT, and enroll/advance SRS as appropriate.

    Mutates ``attempt`` in place (studentId is stamped, and its id may gain a
    disambiguating suffix on a same-millisecond, different-mode collision),
    matching the previous router-inline behavior, so the caller can build its
    response payload from the same object afterward.

    Raises AttemptConflictError or ValueError (both 409-shaped) - the router
    maps both to HTTPException(409).
    """
    attempt.studentId = identity_id
    raw_question_results = [
        result.model_dump(exclude_none=True, exclude_defaults=True) for result in attempt.questionResults
    ]
    research_context = get_research_context(db, identity_id)
    question_results = _validated_question_results(db, attempt)
    existing = repo.find_attempt_by_id(db, attempt.id)
    if existing is not None and existing.get("student_id") != identity_id:
        raise AttemptConflictError("Quiz attempt already belongs to another student.")
    if existing is not None:
        same_attempt = all([
            existing.get("story_id") == attempt.storyId,
            existing.get("student_name") == attempt.studentName,
            existing.get("mode") == attempt.mode,
            existing.get("completed_at") == attempt.completedAt,
            existing.get("total_questions") == attempt.totalQuestions,
            existing.get("correct_count") == attempt.correctCount,
            existing.get("total_time_ms") == attempt.totalTimeMs,
            (existing.get("question_results") or []) == raw_question_results,
        ])
        if not same_attempt:
            if existing.get("mode") == attempt.mode:
                raise AttemptConflictError("Quiz attempt already exists with different response data.")
            # Older generated recorder bundles use a millisecond-only id.
            # If assessment blocks with different modes finish in that
            # same millisecond, preserve both attempts instead of dropping
            # the later block. A same-mode payload remains immutable.
            attempt.id = f"{attempt.id}-{uuid4().hex[:8]}"

    repo.insert_attempt(
        db,
        id=attempt.id,
        story_id=attempt.storyId,
        student_name=attempt.studentName,
        student_id=attempt.studentId,
        mode=attempt.mode,
        completed_at=attempt.completedAt,
        total_questions=attempt.totalQuestions,
        correct_count=attempt.correctCount,
        total_time_ms=attempt.totalTimeMs,
        question_results=raw_question_results,
        progression_policy=research_context.progression_policy.value,
        research_study_id=research_context.study_id,
    )

    # JSONB remains the client-facing attempt source of truth, while this
    # normalized ledger makes every response replayable for BKT calibration.
    normalized_attempt = attempt.model_dump(exclude_none=True)
    normalized_attempt["questionResults"] = question_results
    record_attempt_and_rebuild(
        db,
        normalized_attempt,
        identity_id,
        response_results=question_results,
        research_study_id=research_context.study_id,
    )

    # Spaced-repetition schedule update for review sessions. Scheduling only
    # (BKT already updated above); a review answer advances/resets the
    # word's SM-2 due date, at most once per day. Diagnostic rounds don't.
    if research_context.active and research_context.study_id:
        apply_response_routing(
            db, identity_id, research_context, attempt, question_results,
            now_override=now, day_seconds=day_seconds,
        )
    elif attempt.mode == "maintenance_review":
        apply_srs_updates(
            db, identity_id, _srs_event_results(attempt, question_results),
            now=now, day_seconds=day_seconds,
        )
    _enroll_newly_strong_words(db, identity_id, attempt, now, day_seconds)
    log_core_completion_event(db, identity_id, research_context, attempt, now=now)
    enroll_research_retention_for_attempt(
        db, identity_id, research_context, attempt, now=now, day_seconds=day_seconds,
    )
    enroll_research_probes_for_attempt(db, identity_id, research_context, attempt, now=now)
    return question_results


def record_response(
    db,
    attempt: VocabQuizAttemptRequest,
    identity_id: str,
    *,
    now,
    day_seconds: float,
) -> list[dict]:
    """Persist the answers seen so far without creating a completed attempt.

    The client sends the cumulative answers for the current round using one
    stable quiz id. ``vocab_quiz_responses`` upserts by quiz/order (inside
    record_attempt_and_rebuild), so the eventual completed-attempt write can
    safely replay the same answers.
    """
    attempt.studentId = identity_id
    research_context = get_research_context(db, identity_id)
    question_results = _validated_question_results(db, attempt)
    normalized_attempt = attempt.model_dump(exclude_none=True)
    normalized_attempt["questionResults"] = question_results
    record_attempt_and_rebuild(
        db,
        normalized_attempt,
        identity_id,
        response_results=question_results,
        research_study_id=research_context.study_id,
    )
    # Spaced-repetition schedule update for review sessions. Scheduling only
    # (BKT already updated above); a review answer advances/resets the
    # word's SM-2 due date, at most once per day. Diagnostic rounds don't.
    if research_context.active and research_context.study_id:
        apply_response_routing(
            db, identity_id, research_context, attempt, question_results,
            now_override=now, day_seconds=day_seconds,
        )
    elif attempt.mode == "maintenance_review":
        apply_srs_updates(
            db, identity_id, _srs_event_results(attempt, question_results),
            now=now, day_seconds=day_seconds,
        )
    _enroll_newly_strong_words(db, identity_id, attempt, now, day_seconds)
    log_core_completion_event(db, identity_id, research_context, attempt, now=now)
    enroll_research_retention_for_attempt(
        db, identity_id, research_context, attempt, now=now, day_seconds=day_seconds,
    )
    enroll_research_probes_for_attempt(db, identity_id, research_context, attempt, now=now)
    return question_results
