"""Admin placement blueprint import and student placement assessment APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field

import security.auth as auth
from db import connect_db
from services import placement_data_import_service as data_import_service
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


class PlacementQuestionIdsRequest(BaseModel):
    questionIds: list[str] = Field(..., min_length=1)


class PlacementStudentAccountActivationRequest(BaseModel):
    temporaryPassword: str = Field(..., min_length=8, max_length=100)


async def _read_admin_import(request: Request) -> tuple[list[str] | None, bytes, str]:
    content_type = request.headers.get("content-type", "").casefold()
    if content_type.startswith("application/json"):
        try:
            payload = await request.json()
            if isinstance(payload, list):
                payload = {"questionIds": payload}
            parsed = PlacementQuestionIdsRequest.model_validate(payload)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Provide a non-empty questionIds array.") from exc
        return parsed.questionIds, b"", ""

    form = await request.form()
    file = form.get("file")
    if not hasattr(file, "read"):
        raise HTTPException(status_code=422, detail="Provide a questionIds JSON array or an import file.")
    return None, await file.read(), getattr(file, "filename", "") or ""


@router.get("/api/admin/placement-test")
def get_admin_placement_test(_identity: auth.Identity = Depends(auth.require_admin)):
    with connect_db() as db:
        return service.get_admin_blueprint(db)


@router.get("/api/admin/placement-test/results")
def get_admin_placement_results(_identity: auth.Identity = Depends(auth.require_admin)):
    with connect_db() as db:
        return service.get_admin_import_results(db)


@router.get("/api/admin/placement-test/results/import/sample")
def download_admin_placement_import_sample(_identity: auth.Identity = Depends(auth.require_admin)):
    try:
        with connect_db() as db:
            content = data_import_service.build_sample_workbook(db)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="placement-responses-sample.xlsx"'},
    )


@router.post("/api/admin/placement-test/results/import/preview")
async def preview_admin_placement_import(
    file: UploadFile = File(...),
    _identity: auth.Identity = Depends(auth.require_admin),
):
    content = await file.read()
    with connect_db() as db:
        return data_import_service.preview_import(db, content, file.filename or "")


@router.post("/api/admin/placement-test/results/import/confirm")
async def confirm_admin_placement_import(
    file: UploadFile = File(...),
    _identity: auth.Identity = Depends(auth.require_admin),
):
    content = await file.read()
    try:
        with connect_db() as db:
            return data_import_service.confirm_import(db, content, file.filename or "")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/admin/placement-test/results/import/replace")
async def replace_admin_placement_import(
    file: UploadFile = File(...),
    _identity: auth.Identity = Depends(auth.require_admin),
):
    content = await file.read()
    try:
        with connect_db() as db:
            return data_import_service.replace_import(db, content, file.filename or "")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/admin/placement-test/results/accounts/activate")
def activate_admin_placement_student_accounts(
    payload: PlacementStudentAccountActivationRequest,
    _identity: auth.Identity = Depends(auth.require_admin),
):
    try:
        with connect_db() as db:
            return data_import_service.activate_imported_student_accounts(db, payload.temporaryPassword)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/admin/placement-test/import/preview")
async def preview_placement_test(
    request: Request,
    _identity: auth.Identity = Depends(auth.require_admin),
):
    question_ids, content, filename = await _read_admin_import(request)
    with connect_db() as db:
        if question_ids is not None:
            return service.build_question_ids_preview(db, question_ids)
        return service.build_preview(db, content, filename)


@router.post("/api/admin/placement-test/import/confirm")
async def confirm_placement_test(
    request: Request,
    _identity: auth.Identity = Depends(auth.require_admin),
):
    try:
        question_ids, content, filename = await _read_admin_import(request)
        with connect_db() as db:
            if question_ids is not None:
                return service.replace_from_question_ids(db, question_ids)
            return service.replace_from_upload(db, content, filename)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/placement-test")
def get_student_placement_test(_identity: auth.Identity = Depends(auth.require_student)):
    with connect_db() as db:
        return service.get_student_blueprint(db)


@router.get("/api/placement-test/status")
def get_student_placement_status(identity: auth.Identity = Depends(auth.require_student)):
    try:
        with connect_db() as db:
            return service.get_student_status(db, identity.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
