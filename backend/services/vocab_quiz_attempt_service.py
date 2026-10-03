"""Use-case orchestration for recording and listing vocab quiz attempts.

Coordinates the quiz-attempt repository with BKT mastery updates and SRS
scheduling. Raises domain exceptions (not HTTPException) - the router maps
them to HTTP status codes, per the route/service boundary in
BACKEND_ARCHITECTURE_PLAN.md.
"""
import logging
from typing import Optional
from uuid import uuid4

from analytics.learner_model.bkt.assessment_resolver import resolve_assessment_response
from analytics.learner_model.bkt.mastery import (
    get_vocabulary_mastery,
    lock_student_bkt,
    normalize_word_id,
    record_attempt_and_rebuild,
    response_rows_for_attempt,
    unrecorded_response_rows,
)
from analytics.learner_model.srs_store import apply_srs_updates, enroll_strong_words
from api.schemas.models import VocabQuizAttemptRequest
from repositories import quiz_attempt_repository as repo
from domain.vocabulary.story_scope import canonical_story_id

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
    since: Optional[str] = None,
) -> list[dict]:
    return repo.list_attempts(
        db,
        story_id=story_id,
        student_name=student_name,
        student_id=student_id,
        include_results=include_results,
        since=since,
    )


def _validated_question_results(db, attempt: VocabQuizAttemptRequest) -> list[dict]:
    """Resolve answers to published assessment facts before BKT sees them."""
    # Hold the story lock until the write commits. A vocabulary update either
    # archives this write afterward or finishes first and makes it stale.
    story_id = canonical_story_id(attempt.baseStoryId or attempt.storyId)
    story = db.execute(
        "SELECT vocabulary_version FROM custom_stories WHERE id = %s FOR SHARE", (story_id,),
    ).fetchone()
    if story:
        version = story["vocabulary_version"]
        if (attempt.vocabularyVersion is None and version > 1) or (
            attempt.vocabularyVersion is not None and attempt.vocabularyVersion != version
        ):
            raise ValueError("Lesson vocabulary changed. Reload the lesson and start the quiz again.")
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


def _require_strong_words_for_maintenance(
    db, student_id: str, attempt: VocabQuizAttemptRequest, normalized_attempt: dict, question_results: list[dict],
) -> None:
    """Scheduled maintenance only revisits words the server calls STRONG.

    Call this before the write reaches the ledger. A valid wrong answer takes
    its word out of STRONG, so judging the word after the BKT update would turn
    away exactly the lapse maintenance exists to catch. Answers whose ledger
    slot is already taken (a retry, or the completed attempt replaying a
    partial save) are not judged again for the same reason.
    """
    if attempt.mode != "maintenance_review":
        return
    # The same learner lock the ledger write takes, so the status read here
    # cannot be overtaken by another write for this learner.
    lock_student_bkt(db, student_id)
    new_rows = unrecorded_response_rows(
        db, response_rows_for_attempt(normalized_attempt, student_id, question_results),
    )
    if not new_rows:
        return
    strong = {
        normalize_word_id(row["wordId"])
        for row in get_vocabulary_mastery(db, student_id, story_id=attempt.baseStoryId or attempt.storyId)
        if row["vocabularyState"]["review"]["status"] == "STRONG"
    }
    blocked = sorted({row["word_id"] for row in new_rows} - strong)
    if blocked:
        raise ValueError(
            "Scheduled review only covers words that are currently strong. "
            f"Practise these first: {', '.join(blocked)}."
        )


def _server_evidence_origin(db, student_id: str, requested: str) -> str:
    if requested not in {"real", "synthetic"}:
        raise ValueError("Evidence origin must be real or synthetic.")
    student = db.execute("SELECT is_test_account FROM students WHERE id = %s FOR SHARE", (student_id,)).fetchone()
    if student is None:
        raise ValueError(f"Unknown student: {student_id}")
    return "synthetic" if student["is_test_account"] else requested


def record_attempt(
    db,
    attempt: VocabQuizAttemptRequest,
    identity_id: str,
    *,
    now,
    day_seconds: float,
    evidence_origin: str = "real",
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
    evidence_origin = _server_evidence_origin(db, identity_id, evidence_origin)
    raw_question_results = [
        result.model_dump(exclude_none=True, exclude_defaults=True) for result in attempt.questionResults
    ]
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

    # JSONB remains the client-facing attempt source of truth, while this
    # normalized ledger makes every response replayable for BKT calibration.
    normalized_attempt = attempt.model_dump(exclude_none=True)
    normalized_attempt["questionResults"] = question_results
    _require_strong_words_for_maintenance(db, identity_id, attempt, normalized_attempt, question_results)

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
    )

    record_attempt_and_rebuild(
        db,
        normalized_attempt,
        identity_id,
        response_results=question_results,
        evidence_origin=evidence_origin,
    )

    # Spaced-repetition schedule update for review sessions. Scheduling only
    # (BKT already updated above); a review answer advances/resets the
    # word's SM-2 due date, at most once per day. Diagnostic rounds don't.
    if attempt.mode == "maintenance_review":
        apply_srs_updates(
            db, identity_id, _srs_event_results(attempt, question_results),
            now=now, day_seconds=day_seconds,
        )
    _enroll_newly_strong_words(db, identity_id, attempt, now, day_seconds)
    return question_results


def record_response(
    db,
    attempt: VocabQuizAttemptRequest,
    identity_id: str,
    *,
    now,
    day_seconds: float,
    evidence_origin: str = "real",
) -> list[dict]:
    """Persist the answers seen so far without creating a completed attempt.

    The client sends the cumulative answers for the current round using one
    stable quiz id. ``vocab_quiz_responses`` upserts by quiz/order (inside
    record_attempt_and_rebuild), so the eventual completed-attempt write can
    safely replay the same answers.
    """
    attempt.studentId = identity_id
    evidence_origin = _server_evidence_origin(db, identity_id, evidence_origin)
    question_results = _validated_question_results(db, attempt)
    normalized_attempt = attempt.model_dump(exclude_none=True)
    normalized_attempt["questionResults"] = question_results
    _require_strong_words_for_maintenance(db, identity_id, attempt, normalized_attempt, question_results)
    record_attempt_and_rebuild(
        db,
        normalized_attempt,
        identity_id,
        response_results=question_results,
        evidence_origin=evidence_origin,
    )
    # Spaced-repetition schedule update for review sessions. Scheduling only
    # (BKT already updated above); a review answer advances/resets the
    # word's SM-2 due date, at most once per day. Diagnostic rounds don't.
    if attempt.mode == "maintenance_review":
        apply_srs_updates(
            db, identity_id, _srs_event_results(attempt, question_results),
            now=now, day_seconds=day_seconds,
        )
    _enroll_newly_strong_words(db, identity_id, attempt, now, day_seconds)
    return question_results
