from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from psycopg.types.json import Jsonb

import auth
from config import settings


def _dev_srs_today(today: Optional[str]) -> Optional[datetime]:
    """Dev-only SM-2 time travel for testing the memory cycle without waiting.

    Honors ``?today=YYYY-MM-DD`` ONLY when APP_ENV is "development", so a
    developer can advance/query the spaced-repetition schedule as if days had
    passed. Schedule changes persist in the development database. Returns None
    (the real clock is used downstream) in non-development environment or when
    the value is missing or malformed.

    Keep the same query parameter while answering a review so its schedule
    update uses the simulated date too. Removing it returns to the real clock;
    it does not reset development schedule data. The simulated date is read as
    midnight UTC — precise enough for "pretend a day has passed" testing; use
    ``SRS_DAY_SECONDS`` (see ``_effective_srs_day_seconds``) instead when the
    goal is watching the schedule advance in real time.
    """
    if not today or settings.app_env.strip().lower() != "development":
        return None
    if len(today) != 10 or today[4] != "-" or today[7] != "-":
        return None
    try:
        simulated = date.fromisoformat(today)
    except ValueError:
        return None
    return datetime(simulated.year, simulated.month, simulated.day, tzinfo=timezone.utc)


def _effective_srs_day_seconds() -> float:
    """Dev-only SM-2 interval compression, e.g. SRS_DAY_SECONDS=60 for "1 day = 1 minute".

    Only honored when APP_ENV is "development" — any other environment always
    schedules on a real 24h day regardless of the env var, so a stray setting
    can never shrink a real student's review intervals in production. Lets a
    developer watch the whole due/review cycle happen live (waiting minutes or
    hours instead of days) rather than manually driving ``?today=``.
    """
    if settings.app_env.strip().lower() != "development":
        return DAY_SECONDS
    return settings.srs_day_seconds
from analytics.bkt_assessment_resolver import resolve_assessment_response
from analytics.bkt_mastery import (
    diagnostic_status,
    get_priority_review_words,
    get_vocabulary_mastery,
    record_attempt_and_rebuild,
    seen_item_ids,
)
from analytics.review_queue import build_review_queue
from analytics.srs import DAY_SECONDS
from analytics.srs_store import apply_srs_updates, enroll_strong_words
from database import connect_db, row_to_vocab_quiz_attempt
import main
from main import VocabQuizAttemptRequest

router = APIRouter(dependencies=[Depends(auth.get_current_identity)])


@router.get("/api/vocab-quiz-attempts")
def list_vocab_quiz_attempts(
    story_id: Optional[str] = None,
    student_name: Optional[str] = None,
    student_id: Optional[str] = None,
    include_results: bool = True,
    identity: auth.Identity = Depends(auth.get_current_identity),
):
    if identity.role == "student":
        student_id, student_name = identity.id, None

    # The per-question `question_results` JSONB is the bulk of each row. The
    # teacher dashboard only aggregates attempt-level totals, so it can ask for
    # include_results=false to skip that column - both the DB read and the
    # response payload shrink dramatically over an unfiltered load. Default
    # stays true for the student/admin callers that need the per-question data.
    columns = (
        "id, story_id, student_id, student_name, mode, completed_at, "
        "total_questions, correct_count, total_time_ms"
    )
    if include_results:
        columns += ", question_results"

    query = f"SELECT {columns} FROM vocab_quiz_attempts WHERE 1=1"
    params: list = []
    if story_id:
        query += " AND story_id = %s"
        params.append(story_id)
    if student_name:
        query += " AND student_name = %s"
        params.append(student_name)
    if student_id:
        query += " AND student_id = %s"
        params.append(student_id)
    query += " ORDER BY completed_at DESC"

    with connect_db() as db:
        rows = db.execute(query, params).fetchall()
    return [row_to_vocab_quiz_attempt(row) for row in rows]


def _assert_student_scope(identity: auth.Identity, student_id: str) -> None:
    if identity.role == "student" and identity.id != student_id:
        raise HTTPException(status_code=403, detail="Students may only view their own vocabulary mastery.")


def _validated_question_results(db, attempt: VocabQuizAttemptRequest) -> list[dict]:
    """Resolve answers to published assessment facts before BKT sees them."""
    question_results = []
    for result in attempt.questionResults:
        payload = result.model_dump(exclude_none=True, exclude_defaults=True)
        resolved = resolve_assessment_response(db, attempt, payload)
        if not resolved.get("authoritativeResolved"):
            main.logger.warning(
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


def _enroll_newly_strong_words(db, student_id: str, attempt: VocabQuizAttemptRequest, today: Optional[str]) -> None:
    """Start SRS only after the server marks a current-lesson word STRONG."""
    story_id = attempt.baseStoryId or attempt.storyId
    enroll_strong_words(
        db,
        student_id,
        get_vocabulary_mastery(db, student_id, story_id=story_id),
        now=_dev_srs_today(today),
        day_seconds=_effective_srs_day_seconds(),
    )


@router.get("/api/students/{student_id}/weak-words")
def get_student_priority_review_words(
    student_id: str,
    review_count: Optional[int] = None,
    story_id: Optional[str] = None,
    include_all: bool = False,
    identity: auth.Identity = Depends(auth.get_current_identity),
):
    """Return learner-relative Bottom-K BKT review priorities."""
    _assert_student_scope(identity, student_id)
    options = {key: value for key, value in (("reviewCount", review_count), ("storyId", story_id)) if value is not None}
    if include_all:
        options["includeAllWeak"] = True
    with connect_db() as db:
        return get_priority_review_words(db, student_id, options)


@router.get("/api/students/{student_id}/review-queue")
async def get_student_review_queue(
    student_id: str,
    review_count: Optional[int] = None,
    story_id: Optional[str] = None,
    include_all: bool = False,
    today: Optional[str] = None,
    identity: auth.Identity = Depends(auth.get_current_identity),
):
    """Weak words (BKT) ∪ due words (SM-2), tagged weak|due for the UI.

    Scheduling-only: BKT mastery is unchanged; this just adds SM-2 due words to
    the existing weak-word priorities so mastered-but-due words resurface.
    """
    _assert_student_scope(identity, student_id)
    options = {key: value for key, value in (("reviewCount", review_count), ("storyId", story_id)) if value is not None}
    if include_all:
        options["includeAllWeak"] = True
    with connect_db() as db:
        return build_review_queue(db, student_id, options, now=_dev_srs_today(today))


@router.get("/api/students/{student_id}/vocabulary-mastery")
def get_student_vocabulary_mastery(
    student_id: str,
    story_id: Optional[str] = None,
    identity: auth.Identity = Depends(auth.get_current_identity),
):
    _assert_student_scope(identity, student_id)
    with connect_db() as db:
        return {
            **diagnostic_status(db, student_id, story_id=story_id),
            "words": get_vocabulary_mastery(db, student_id, story_id=story_id),
        }


@router.get("/api/students/{student_id}/vocabulary-mastery/{word_id:path}/seen-items")
def get_seen_vocabulary_items(
    student_id: str,
    word_id: str,
    identity: auth.Identity = Depends(auth.get_current_identity),
):
    _assert_student_scope(identity, student_id)
    with connect_db() as db:
        return {"itemIds": seen_item_ids(db, student_id, word_id)}


@router.get("/api/vocab-quiz-attempts/weak-words")
def get_weak_words(
    story_id: str,
    include_all: bool = False,
    identity: auth.Identity = Depends(auth.require_student),
):
    """Compatibility-shaped response backed by guarded standard BKT."""
    with connect_db() as db:
        result = get_priority_review_words(db, identity.id, {"storyId": story_id, "includeAllWeak": include_all})
    return {
        "words": [word["word"] for word in result["words"]],
        "diagnostic": {
            key: result[key]
            for key in (
                "unlocked", "requiredDiagnosticQuizzes", "completedDiagnosticQuizzes",
                "requiredWords", "sufficientWords", "wordCoverage", "roundPresence", "diagnosticComplete",
            )
        },
    }


@router.post("/api/vocab-quiz-attempts")
def create_vocab_quiz_attempt(
    attempt: VocabQuizAttemptRequest,
    today: Optional[str] = None,
    identity: auth.Identity = Depends(auth.require_student),
):
    attempt.studentId = identity.id
    raw_question_results = [result.model_dump(exclude_none=True, exclude_defaults=True) for result in attempt.questionResults]
    with connect_db() as db:
        question_results = _validated_question_results(db, attempt)
        existing = db.execute(
            "SELECT * FROM vocab_quiz_attempts WHERE id = %s",
            (attempt.id,),
        ).fetchone()
        if existing is not None and existing.get("student_id") != identity.id:
            raise HTTPException(
                status_code=409,
                detail="Quiz attempt already belongs to another student.",
            )
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
                    raise HTTPException(
                        status_code=409,
                        detail="Quiz attempt already exists with different response data.",
                    )
                # Older generated recorder bundles use a millisecond-only id.
                # If assessment blocks with different modes finish in that
                # same millisecond, preserve both attempts instead of dropping
                # the later block. A same-mode payload remains immutable.
                attempt.id = f"{attempt.id}-{uuid4().hex[:8]}"
        db.execute(
            """
            INSERT INTO vocab_quiz_attempts
                (id, story_id, student_name, student_id, mode, completed_at,
                 total_questions, correct_count, total_time_ms, question_results)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                attempt.id,
                attempt.storyId,
                attempt.studentName,
                attempt.studentId,
                attempt.mode,
                attempt.completedAt,
                attempt.totalQuestions,
                attempt.correctCount,
                attempt.totalTimeMs,
                Jsonb(raw_question_results),
            ),
        )
        # JSONB remains the client-facing attempt source of truth, while this
        # normalized ledger makes every response replayable for BKT calibration.
        normalized_attempt = attempt.model_dump(exclude_none=True)
        normalized_attempt["questionResults"] = question_results
        try:
            record_attempt_and_rebuild(db, normalized_attempt, identity.id, response_results=question_results)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        # Spaced-repetition schedule update for review sessions. Scheduling only
        # (BKT already updated above); a review answer advances/resets the
        # word's SM-2 due date, at most once per day. Diagnostic rounds don't.
        if attempt.mode == "maintenance_review":
            apply_srs_updates(
                db, identity.id, _srs_event_results(attempt, question_results),
                now=_dev_srs_today(today), day_seconds=_effective_srs_day_seconds(),
            )
        _enroll_newly_strong_words(db, identity.id, attempt, today)
    payload = attempt.model_dump(exclude_none=True)
    payload["questionResults"] = raw_question_results
    # Keep the nullable field present for clients that use the response as a
    # round-trip representation of an attempt without a selected mode.
    payload.setdefault("mode", attempt.mode)
    return payload


@router.post("/api/vocab-quiz-responses")
async def record_vocab_quiz_response(
    attempt: VocabQuizAttemptRequest,
    today: Optional[str] = None,
    identity: auth.Identity = Depends(auth.require_student),
):
    """Persist the answers seen so far without creating a completed attempt.

    The client sends the cumulative answers for the current round using one
    stable quiz id. ``vocab_quiz_responses`` upserts by quiz/order, so the
    eventual completed-attempt write can safely replay the same answers.
    """
    attempt.studentId = identity.id
    with connect_db() as db:
        question_results = _validated_question_results(db, attempt)
        normalized_attempt = attempt.model_dump(exclude_none=True)
        normalized_attempt["questionResults"] = question_results
        try:
            record_attempt_and_rebuild(db, normalized_attempt, identity.id, response_results=question_results)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        # Spaced-repetition schedule update for review sessions. Scheduling only
        # (BKT already updated above); a review answer advances/resets the
        # word's SM-2 due date, at most once per day. Diagnostic rounds don't.
        if attempt.mode == "maintenance_review":
            apply_srs_updates(
                db, identity.id, _srs_event_results(attempt, question_results),
                now=_dev_srs_today(today), day_seconds=_effective_srs_day_seconds(),
            )
        _enroll_newly_strong_words(db, identity.id, attempt, today)
    return {"acceptedResponses": len(question_results)}
