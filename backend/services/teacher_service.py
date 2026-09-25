"""Use-case orchestration for the teacher roster and login endpoints.

Coordinates the teacher repository with password hashing/verification
(security.auth) and the idempotency/uniqueness decisions that used to live
inline in routers/teachers.py. Raises TeacherServiceError (not
HTTPException) - the router maps it to an HTTP status code. Token issuance
and session-cookie writes stay in the router since they operate on the
FastAPI ``Response`` object.
"""
import uuid

from psycopg.errors import UniqueViolation

import security.auth as auth
from repositories import teacher_repository as repo
from repositories.database import row_to_teacher


class TeacherServiceError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def list_teachers(db) -> list[dict]:
    rows = repo.find_all(db)
    return [row_to_teacher(row) for row in rows]


def create_teacher(db, name: str, password: str) -> dict:
    name = name.strip()
    auth.validate_password_policy(password)
    if repo.exists_name_ci(db, name):
        raise TeacherServiceError(409, "Teacher already exists.")
    try:
        row = repo.insert(db, str(uuid.uuid4()), name, auth.hash_password(password))
    except UniqueViolation as exc:
        raise TeacherServiceError(409, "Teacher already exists.") from exc
    return row_to_teacher(row)


def authenticate_teacher(db, name: str, password: str) -> dict:
    """Verify credentials, silently upgrading a legacy password hash on
    success, and return the raw teacher row for the router to build a
    session from.
    """
    row = repo.find_by_name_ci(db, name.strip())
    if row is None:
        raise TeacherServiceError(404, "Teacher not found")
    if row["status"] != "active":
        raise TeacherServiceError(403, "Teacher account is inactive")
    if row.get("password_reset_required"):
        raise TeacherServiceError(403, "Teacher password reset required")

    valid, replacement_hash = auth.verify_password(row.get("password"), password)
    if not valid:
        raise TeacherServiceError(401, "Wrong password")
    if replacement_hash is not None:
        repo.update_password_hash(db, row["id"], replacement_hash)

    return row


def update_teacher(db, teacher_id: str, request) -> dict:
    set_clauses: list[str] = []
    params: list = []
    if request.name is not None:
        name = request.name.strip()
        if not name:
            raise TeacherServiceError(400, "Provide a teacher name.")
        duplicate = repo.find_name_conflict(db, name, teacher_id)
        if duplicate is not None:
            raise TeacherServiceError(409, "Teacher already exists.")
        set_clauses.append("name = %s")
        params.append(name)
    if request.password is not None:
        auth.validate_password_policy(request.password)
        set_clauses.extend(["password = %s", "password_reset_required = false"])
        params.append(auth.hash_password(request.password))
    if request.status is not None:
        set_clauses.append("status = %s")
        params.append(request.status)
    if not set_clauses:
        raise TeacherServiceError(400, "No teacher changes supplied.")

    try:
        row = repo.update_fields(db, teacher_id, set_clauses, params)
    except UniqueViolation as exc:
        raise TeacherServiceError(409, "Teacher already exists.") from exc
    if row is None:
        raise TeacherServiceError(404, "Teacher not found")
    return row_to_teacher(row)


def delete_teacher(db, teacher_id: str) -> None:
    row = repo.delete(db, teacher_id)
    if row is None:
        raise TeacherServiceError(404, "Teacher not found")
