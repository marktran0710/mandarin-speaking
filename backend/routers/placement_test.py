"""Admin placement blueprint import and student placement assessment APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

import security.auth as auth
from db import connect_db
from services import placement_test_service as service


router = APIRouter(tags=["placement-test"])


class PlacementResponse(BaseModel):
    questionId: str = Field(..., min_length=1, max_length=256)
    selectedAnswer: str = Field(..., min_length=1, max_length=500)
    timeMs: int = Field(default=0, ge=0)
    answeredAt: str | None = None


class PlacementCompleteRequest(BaseModel):
    attemptId: str | None = None
    responses: list[PlacementResponse] = Field(default_factory=list)
    completedAt: str | None = None


@router.get("/api/admin/placement-test")
def get_admin_placement_test(_identity: auth.Identity = Depends(auth.require_admin)):
    with connect_db() as db:
        return service.get_admin_blueprint(db)


@router.get("/api/admin/placement-test/results")
def get_admin_placement_results(_identity: auth.Identity = Depends(auth.require_admin)):
    with connect_db() as db:
        return service.get_admin_import_results(db)


@router.post("/api/admin/placement-test/import/preview")
async def preview_placement_test(
    file: UploadFile = File(...),
    _identity: auth.Identity = Depends(auth.require_admin),
):
    content = await file.read()
    with connect_db() as db:
        return service.build_preview(db, content, file.filename or "")


@router.post("/api/admin/placement-test/import/confirm")
async def confirm_placement_test(
    file: UploadFile = File(...),
    _identity: auth.Identity = Depends(auth.require_admin),
):
    content = await file.read()
    try:
        with connect_db() as db:
            return service.replace_from_upload(db, content, file.filename or "")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/placement-test")
def get_student_placement_test(_identity: auth.Identity = Depends(auth.require_student)):
    with connect_db() as db:
        return service.get_student_blueprint(db)


@router.post("/api/placement-test/attempts")
def start_student_placement_test(
    payload: PlacementCompleteRequest | None = None,
    identity: auth.Identity = Depends(auth.require_student),
):
    try:
        with connect_db() as db:
            if payload and payload.attemptId:
                return service.complete_attempt(
                    db,
                    identity.id,
                    payload.attemptId,
                    [response.model_dump(exclude_none=True) for response in payload.responses],
                    payload.completedAt,
                )
            return service.start_attempt(db, identity.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/placement-test/attempts/{attempt_id}/complete")
def complete_student_placement_test(
    attempt_id: str,
    payload: PlacementCompleteRequest,
    identity: auth.Identity = Depends(auth.require_student),
):
    try:
        with connect_db() as db:
            return service.complete_attempt(
                db,
                identity.id,
                attempt_id,
                [response.model_dump(exclude_none=True) for response in payload.responses],
                payload.completedAt,
            )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
