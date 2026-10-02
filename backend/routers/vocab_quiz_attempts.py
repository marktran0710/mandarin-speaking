from datetime import date, datetime, timedelta, timezone
from typing import Optional

from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Query, Request

import security.auth as auth
import services.vocab_quiz_attempt_service as vocab_quiz_attempt_service
from services import algorithm_verifier_service
from analytics.learner_model.srs import DAY_SECONDS
from config import settings
from db import connect_db
from api.schemas.models import VocabQuizAttemptRequest


router = APIRouter()


@dataclass(frozen=True)
class _QuizWriteContext:
    identity: auth.Identity
    evidence_origin: str
    run_id: str | None = None
    step: int | None = None


def _quiz_write_context(
    request: Request,
    identity: auth.Identity = Depends(auth.get_current_identity),
) -> _QuizWriteContext:
    run_id = request.headers.get("X-Algorithm-Verifier-Run")
    verifier_student = request.headers.get("X-Algorithm-Verifier-Student")
    raw_step = request.headers.get("X-Algorithm-Verifier-Step")
    if not any((run_id, verifier_student, raw_step)):
        if identity.role != "student":
            raise HTTPException(status_code=403, detail="Student account required.")
        return _QuizWriteContext(identity=identity, evidence_origin="real")
    if identity.role != "admin":
        raise HTTPException(status_code=403, detail="Verifier context requires an authenticated Admin.")
    if not run_id or not verifier_student or raw_step is None:
        raise HTTPException(status_code=403, detail="Verifier context headers are incomplete.")
    try:
        step = int(raw_step)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Verifier context step is invalid.") from exc
    return _QuizWriteContext(
        identity=auth.Identity(role="student", id=algorithm_verifier_service.INTEGRATION_STUDENT_ID),
        evidence_origin="synthetic",
        run_id=run_id,
        step=step,
    )


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
    since_days: Optional[int] = Query(default=None, ge=1, le=3650),
    identity: auth.Identity = Depends(auth.get_current_identity),
):
    if identity.role == "student":
        student_id, student_name = identity.id, None

    since = None
    if since_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
        # Match the exact shape `completed_at` is always written in (the
        # client's `Date.toISOString()`) so the repository's text comparison
        # stays a valid chronological cutoff.
        since = cutoff.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    with connect_db() as db:
        return vocab_quiz_attempt_service.list_attempts(
            db,
            story_id=story_id,
            student_name=student_name,
            student_id=student_id,
            include_results=include_results,
            since=since,
        )


@router.post("/api/vocab-quiz-attempts")
def create_vocab_quiz_attempt(
    attempt: VocabQuizAttemptRequest,
    today: Optional[str] = None,
    context: _QuizWriteContext = Depends(_quiz_write_context),
):
    # The client-facing response echoes exactly what the client sent, not the
    # server-resolved/authoritative version the service validates internally.
    raw_question_results = [
        result.model_dump(exclude_none=True, exclude_defaults=True) for result in attempt.questionResults
    ]
    with connect_db() as db:
        try:
            if context.evidence_origin == "synthetic":
                algorithm_verifier_service.lock_and_validate_verifier_context(
                    db,
                    run_id=context.run_id or "",
                    student_id=context.identity.id,
                    step=context.step if context.step is not None else -1,
                )
            vocab_quiz_attempt_service.record_attempt(
                db, attempt, context.identity.id,
                now=_dev_srs_today(today), day_seconds=_effective_srs_day_seconds(),
                evidence_origin=context.evidence_origin,
            )
            if context.evidence_origin == "synthetic":
                algorithm_verifier_service.advance_verifier_context(db, step=context.step or 0)
        except (vocab_quiz_attempt_service.AttemptConflictError, ValueError, algorithm_verifier_service.AlgorithmVerifierError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    payload = attempt.model_dump(exclude_none=True)
    payload["questionResults"] = raw_question_results
    # Keep the nullable field present for clients that use the response as a
    # round-trip representation of an attempt without a selected mode.
    payload.setdefault("mode", attempt.mode)
    payload["roundCompleted"] = True
    return payload


@router.post("/api/vocab-quiz-responses")
def record_vocab_quiz_response(
    attempt: VocabQuizAttemptRequest,
    today: Optional[str] = None,
    context: _QuizWriteContext = Depends(_quiz_write_context),
):
    """Persist the answers seen so far without creating a completed attempt."""
    with connect_db() as db:
        try:
            if context.evidence_origin == "synthetic":
                algorithm_verifier_service.lock_and_validate_verifier_context(
                    db,
                    run_id=context.run_id or "",
                    student_id=context.identity.id,
                    step=context.step if context.step is not None else -1,
                )
            question_results = vocab_quiz_attempt_service.record_response(
                db, attempt, context.identity.id,
                now=_dev_srs_today(today), day_seconds=_effective_srs_day_seconds(),
                evidence_origin=context.evidence_origin,
            )
            if context.evidence_origin == "synthetic":
                algorithm_verifier_service.advance_verifier_context(db, step=context.step or 0)
        except (ValueError, algorithm_verifier_service.AlgorithmVerifierError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"acceptedResponses": len(question_results)}
