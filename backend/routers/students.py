from fastapi import APIRouter, Depends, HTTPException, Request, Response

import security.auth as auth
import services.student_service as student_service
from db import connect_db
from repositories.database import row_to_student
from main import (
    StudentCreateRequest,
    StudentLoginRequest,
    StudentPasswordResetRequest,
    StudentUpdateRequest,
)

router = APIRouter()


@router.get("/api/students/{student_id}/overview")
def get_student_overview(
    student_id: str,
    identity: auth.Identity = Depends(auth.get_current_identity),
):
    """One request for the student home's three lists.

    "My Stories" previously fanned out to `/api/story-submissions`,
    `/api/vocab-quiz-attempts` and `/api/audio-records` in parallel — three
    auth checks and three pooled connections per visit. This serves all three
    for one student over a single connection. Submissions and quiz attempts
    come back trimmed (no `scenes` / `question_results` JSONB): the page only
    reads earned stars and which stories were touched.

    The three tables are independent (no join), so the reads are batched in a
    psycopg pipeline — sent together and read back after a single round-trip
    to Postgres rather than three sequential query round-trips. Every filter
    is covered by a 0027 composite index (student_id + the ORDER BY column).
    """
    if identity.role == "student" and identity.id != student_id:
        raise HTTPException(status_code=403, detail="Students may only view their own overview.")

    with connect_db() as db:
        return student_service.get_overview(db, student_id)


@router.get("/api/students")
def list_students(
    identity: auth.Identity = Depends(auth.require_teacher_or_admin),
):
    with connect_db() as db:
        return student_service.list_students(db, identity.role)


@router.post("/api/students")
def create_student(
    request: StudentCreateRequest,
    identity: auth.Identity = Depends(auth.require_admin),
):
    with connect_db() as db:
        try:
            return student_service.create_student(db, request.name, request.password)
        except student_service.StudentServiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/api/students/login")
def login_student(
    request: StudentLoginRequest,
    response: Response,
    http_request: Request,
):
    """Verify a student password and issue a signed session cookie."""
    if not (request.studentId or (request.name and request.name.strip())):
        raise HTTPException(status_code=400, detail="Provide a student id or name.")
    client_ip = http_request.client.host if http_request.client else "unknown"
    auth.check_login_rate_limit(f"student:{client_ip}:{(request.studentId or request.name or '').strip().lower()}")

    with connect_db() as db:
        try:
            row = student_service.authenticate_student(
                db, request.studentId, request.name, request.password
            )
        except student_service.StudentServiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    token = auth.issue_token("student", row["id"])
    auth.set_session_cookie(response, token, "student")
    return row_to_student(row)


@router.patch("/api/students/{student_id}/password")
def reset_student_password(
    student_id: str,
    request: StudentPasswordResetRequest,
    identity: auth.Identity = Depends(auth.require_admin),
):
    with connect_db() as db:
        try:
            return student_service.reset_student_password(db, student_id, request.password)
        except student_service.StudentServiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.patch("/api/students/{student_id}")
def update_student(
    student_id: str,
    request: StudentUpdateRequest,
    identity: auth.Identity = Depends(auth.require_admin),
):
    with connect_db() as db:
        try:
            return student_service.update_student(db, student_id, request)
        except student_service.StudentServiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/api/students/logout")
def logout_student(response: Response):
    auth.clear_session_cookie(response, "student")
    return {"loggedOut": True}


@router.delete("/api/students/{student_id}")
def delete_student(
    student_id: str,
    identity: auth.Identity = Depends(auth.require_admin),
):
    with connect_db() as db:
        try:
            student_service.delete_student(db, student_id)
        except student_service.StudentServiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return {"id": student_id, "deleted": True}
