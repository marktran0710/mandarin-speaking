from fastapi import APIRouter, Depends, HTTPException, Request, Response

import security.auth as auth
import services.teacher_service as teacher_service
from db import connect_db
from repositories.database import row_to_teacher
from main import TeacherCreateRequest, TeacherLoginRequest, TeacherUpdateRequest

router = APIRouter()


@router.get("/api/teachers")
def list_teachers(identity: auth.Identity = Depends(auth.require_teacher_or_admin)):
    with connect_db() as db:
        return teacher_service.list_teachers(db)


@router.post("/api/teachers")
def create_teacher(
    request: TeacherCreateRequest,
    identity: auth.Identity = Depends(auth.require_admin),
):
    with connect_db() as db:
        try:
            return teacher_service.create_teacher(db, request.name, request.password)
        except teacher_service.TeacherServiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/api/teachers/login")
def login_teacher(
    request: TeacherLoginRequest,
    response: Response,
    http_request: Request,
):
    client_ip = http_request.client.host if http_request.client else "unknown"
    auth.check_login_rate_limit(f"teacher:{client_ip}:{request.name.strip().lower()}")
    with connect_db() as db:
        try:
            row = teacher_service.authenticate_teacher(db, request.name, request.password)
        except teacher_service.TeacherServiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    token = auth.issue_token("teacher", row["id"])
    auth.set_session_cookie(response, token, "teacher")
    return row_to_teacher(row)


@router.post("/api/teachers/logout")
def logout_teacher(response: Response):
    auth.clear_session_cookie(response, "teacher")
    return {"loggedOut": True}


@router.patch("/api/teachers/{teacher_id}")
def update_teacher(
    teacher_id: str,
    request: TeacherUpdateRequest,
    identity: auth.Identity = Depends(auth.require_admin),
):
    with connect_db() as db:
        try:
            return teacher_service.update_teacher(db, teacher_id, request)
        except teacher_service.TeacherServiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.delete("/api/teachers/{teacher_id}")
def delete_teacher(
    teacher_id: str,
    identity: auth.Identity = Depends(auth.require_admin),
):
    with connect_db() as db:
        try:
            teacher_service.delete_teacher(db, teacher_id)
        except teacher_service.TeacherServiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return {"id": teacher_id, "deleted": True}
