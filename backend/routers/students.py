import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from psycopg.errors import UniqueViolation

import auth
from database import connect_db, row_to_student
from main import (
    StudentCreateRequest,
    StudentLoginRequest,
    StudentPasswordResetRequest,
    StudentUpdateRequest,
)

router = APIRouter()


@router.get("/api/students")
async def list_students(
    identity: auth.Identity = Depends(auth.require_teacher_or_admin),
):
    with connect_db() as db:
        # Postgres has no COLLATE NOCASE; lower() reproduces SQLite's
        # case-insensitive roster ordering (backed by ix_students_lower_name).
        rows = db.execute("SELECT * FROM students ORDER BY lower(name)").fetchall()
    return [row_to_student(row) for row in rows]


@router.post("/api/students")
async def create_student(
    request: StudentCreateRequest,
    identity: auth.Identity = Depends(auth.require_admin),
):
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Provide a student name.")
    auth.validate_password_policy(request.password)

    with connect_db() as db:
        existing = db.execute(
            "SELECT * FROM students WHERE lower(name) = lower(%s)",
            (name,),
        ).fetchone()
        if existing is not None:
            # Idempotent: re-adding a name already on the roster just hands
            # back its existing id instead of erroring, so a teacher can
            # re-submit the roster form without worrying about duplicates.
            return row_to_student(existing)

        student_id = str(uuid.uuid4())
        try:
            created = db.execute(
                "INSERT INTO students (id, name, password) VALUES (%s, %s, %s) RETURNING *",
                (student_id, name, auth.hash_password(request.password)),
            ).fetchone()
        except UniqueViolation as exc:
            raise HTTPException(status_code=409, detail="Student already exists.") from exc
    return row_to_student(created)


@router.post("/api/students/login")
async def login_student(
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
        if request.studentId:
            row = db.execute(
                "SELECT * FROM students WHERE id = %s", (request.studentId,)
            ).fetchone()
        else:
            row = db.execute(
                "SELECT * FROM students WHERE lower(name) = lower(%s)",
                (request.name.strip(),),
            ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Student not found")
    if row.get("status") != "active":
        raise HTTPException(status_code=403, detail="Student account is inactive")
    if row.get("password_reset_required"):
        raise HTTPException(status_code=403, detail="Student password reset required")

    valid, replacement_hash = auth.verify_password(row.get("password"), request.password)
    if not valid:
        raise HTTPException(status_code=401, detail="Wrong password")
    if replacement_hash is not None:
        with connect_db() as db:
            db.execute(
                "UPDATE students SET password = %s WHERE id = %s",
                (replacement_hash, row["id"]),
            )

    token = auth.issue_token("student", row["id"])
    auth.set_session_cookie(response, token, "student")
    return row_to_student(row)


@router.patch("/api/students/{student_id}/password")
async def reset_student_password(
    student_id: str,
    request: StudentPasswordResetRequest,
    identity: auth.Identity = Depends(auth.require_admin),
):
    auth.validate_password_policy(request.password)
    with connect_db() as db:
        row = db.execute(
            "UPDATE students SET password = %s, password_reset_required = false WHERE id = %s RETURNING *",
            (auth.hash_password(request.password), student_id),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Student not found")
    return row_to_student(row)


@router.patch("/api/students/{student_id}")
async def update_student(
    student_id: str,
    request: StudentUpdateRequest,
    identity: auth.Identity = Depends(auth.require_admin),
):
    updates, params = [], []
    if request.name is not None:
        name = request.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Provide a student name.")
        with connect_db() as db:
            duplicate = db.execute(
                "SELECT 1 FROM students WHERE lower(name) = lower(%s) AND id <> %s",
                (name, student_id),
            ).fetchone()
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="Student already exists.")
        updates.append("name = %s")
        params.append(name)
    if request.password is not None:
        auth.validate_password_policy(request.password)
        updates.extend(["password = %s", "password_reset_required = false"])
        params.append(auth.hash_password(request.password))
    if request.status is not None:
        updates.append("status = %s")
        params.append(request.status)
    if not updates:
        raise HTTPException(status_code=400, detail="No student changes supplied.")
    params.append(student_id)
    try:
        with connect_db() as db:
            row = db.execute(
                f"UPDATE students SET {', '.join(updates)} WHERE id = %s RETURNING *",
                tuple(params),
            ).fetchone()
    except UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="Student already exists.") from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Student not found")
    return row_to_student(row)


@router.post("/api/students/logout")
async def logout_student(response: Response):
    auth.clear_session_cookie(response, "student")
    return {"loggedOut": True}


@router.delete("/api/students/{student_id}")
async def delete_student(
    student_id: str,
    identity: auth.Identity = Depends(auth.require_admin),
):
    with connect_db() as db:
        row = db.execute(
            "DELETE FROM students WHERE id = %s RETURNING id", (student_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Student not found")
    return {"id": student_id, "deleted": True}
