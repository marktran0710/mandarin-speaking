from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

import security.auth as auth
import services.vocab_quiz_attempt_service as vocab_quiz_attempt_service
from application.vocabulary_research import get_research_context
from analytics.learner_model.srs import DAY_SECONDS
from config import settings
from db import connect_db
from api.schemas.models import VocabQuizAttemptRequest


router = APIRouter()


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
    midnight UTC ??precise enough for "pretend a day has passed" testing; use
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

    Only honored when APP_ENV is "development" ??any other environment always
    schedules on a real 24h day regardless of the env var, so a stray setting
    can never shrink a real student's review intervals in production. Lets a
    developer watch the whole due/review cycle happen live (waiting minutes or
    hours instead of days) rather than manually driving ``?today=``.
    """
    if settings.app_env.strip().lower() != "development":
        return DAY_SECONDS
    return settings.srs_day_seconds


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

    with connect_db() as db:
        return vocab_quiz_attempt_service.list_attempts(
            db,
            story_id=story_id,
            student_name=student_name,
            student_id=student_id,
            include_results=include_results,
        )


@router.post("/api/vocab-quiz-attempts")
def create_vocab_quiz_attempt(
    attempt: VocabQuizAttemptRequest,
    today: Optional[str] = None,
    identity: auth.Identity = Depends(auth.require_student),
):
    # The client-facing response echoes exactly what the client sent, not the
    # server-resolved/authoritative version the service validates internally.
    raw_question_results = [
        result.model_dump(exclude_none=True, exclude_defaults=True) for result in attempt.questionResults
    ]
    with connect_db() as db:
        try:
            vocab_quiz_attempt_service.record_attempt(
                db, attempt, identity.id,
                now=_dev_srs_today(today), day_seconds=_effective_srs_day_seconds(),
            )
        except (vocab_quiz_attempt_service.AttemptConflictError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        research_context = get_research_context(db, identity.id)
    payload = attempt.model_dump(exclude_none=True)
    payload["questionResults"] = raw_question_results
    # Keep the nullable field present for clients that use the response as a
    # round-trip representation of an attempt without a selected mode.
    payload.setdefault("mode", attempt.mode)
    payload["progressionPolicy"] = research_context.progression_policy.value
    payload["roundCompleted"] = True
    payload["researchStudyId"] = research_context.study_id
    return payload


@router.post("/api/vocab-quiz-responses")
async def record_vocab_quiz_response(
    attempt: VocabQuizAttemptRequest,
    today: Optional[str] = None,
    identity: auth.Identity = Depends(auth.require_student),
):
    """Persist the answers seen so far without creating a completed attempt."""
    with connect_db() as db:
        try:
            question_results = vocab_quiz_attempt_service.record_response(
                db, attempt, identity.id,
                now=_dev_srs_today(today), day_seconds=_effective_srs_day_seconds(),
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"acceptedResponses": len(question_results)}
