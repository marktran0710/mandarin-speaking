"""Student endpoints for the unified personalized + scheduled review session."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

import security.auth as auth
from api.schemas.models import VocabReviewSessionAnswerRequest
from db import connect_db
from routers.vocab_quiz_attempts import _dev_srs_today, _effective_srs_day_seconds
from services import vocab_review_session_service as service


router = APIRouter()


def _require_owner(identity: auth.Identity, student_id: str) -> None:
    if identity.id != student_id:
        raise HTTPException(status_code=403, detail="Students may only review their own vocabulary.")


def _raise_session_error(error: service.ReviewSessionConflictError) -> None:
    code = "STALE_VOCABULARY" if isinstance(error, service.ReviewSessionStaleError) else "REVIEW_SESSION_CONFLICT"
    raise HTTPException(status_code=409, detail={"code": code, "message": str(error)}) from error


@router.post("/api/students/{student_id}/review-sessions")
def start_or_resume_review_session(
    student_id: str,
    today: str | None = None,
    identity: auth.Identity = Depends(auth.require_student),
):
    """Resume the active session or create a capped session from all learned lessons."""
    _require_owner(identity, student_id)
    with connect_db() as db:
        try:
            return service.create_or_resume_review_session(
                db,
                student_id,
                now=_dev_srs_today(today) or datetime.now(timezone.utc),
            )
        except service.ReviewSessionConflictError as exc:
            _raise_session_error(exc)


@router.get("/api/students/{student_id}/review-sessions/{session_id}")
def read_review_session(
    student_id: str,
    session_id: str,
    identity: auth.Identity = Depends(auth.require_student),
):
    _require_owner(identity, student_id)
    with connect_db() as db:
        try:
            return service.get_review_session(db, student_id, session_id)
        except service.ReviewSessionConflictError as exc:
            _raise_session_error(exc)


@router.post("/api/students/{student_id}/review-sessions/{session_id}/answers")
def answer_review_session_question(
    student_id: str,
    session_id: str,
    answer: VocabReviewSessionAnswerRequest,
    today: str | None = None,
    identity: auth.Identity = Depends(auth.require_student),
):
    _require_owner(identity, student_id)
    with connect_db() as db:
        try:
            return service.answer_review_session_question(
                db,
                student_id,
                session_id,
                answer.slotId,
                answer.selectedAnswer.strip(),
                answer.responseTimeMs,
                now=_dev_srs_today(today) or datetime.now(timezone.utc),
                day_seconds=_effective_srs_day_seconds(),
            )
        except service.ReviewSessionConflictError as exc:
            _raise_session_error(exc)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail={"code": "REVIEW_SESSION_CONFLICT", "message": str(exc)}) from exc


@router.post("/api/students/{student_id}/review-sessions/{session_id}/defer")
def defer_review_session(
    student_id: str,
    session_id: str,
    identity: auth.Identity = Depends(auth.require_student),
):
    _require_owner(identity, student_id)
    with connect_db() as db:
        try:
            return service.defer_review_session(db, student_id, session_id, now=datetime.now(timezone.utc))
        except service.ReviewSessionConflictError as exc:
            _raise_session_error(exc)
