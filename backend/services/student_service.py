"""Use-case orchestration for the student roster, login, and self-service
account endpoints.

Coordinates the student repository with password hashing/verification
(security.auth) and the idempotency/visibility/ownership decisions that used
to live inline in routers/students.py. Raises StudentServiceError (not
HTTPException) - the router maps it to an HTTP status code. Token issuance
and session-cookie writes stay in the router since they operate on the
FastAPI ``Response`` object.
"""
import uuid
from typing import Optional

from psycopg.errors import UniqueViolation

import security.auth as auth
from repositories import student_repository as repo
from repositories.database import (
    delete_student_cascade,
    row_to_audio_record,
    row_to_student,
)

_OVERVIEW_AUDIO_LIMIT = 1000


class StudentServiceError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _overview_submission(row: dict) -> dict:
    return {
        "id": row["id"],
        "storyId": row["story_id"],
        "storyTitle": row["story_title"],
        "studentName": row["student_name"],
        "studentId": row.get("student_id"),
        "submittedAt": row["submitted_at"],
        "concatenatedAudioUrl": row.get("concatenated_audio_url"),
        "reviewStatus": row.get("review_status") or "pending",
        "teacherNote": row.get("teacher_note"),
        "scenes": [],
        "storyFeedback": None,
    }


def _overview_quiz_attempt(row: dict) -> dict:
    return {
        "id": row["id"],
        "storyId": row["story_id"],
        "studentName": row["student_name"],
        "studentId": row.get("student_id"),
        "mode": row.get("mode"),
        "completedAt": row["completed_at"],
        "totalQuestions": row["total_questions"],
        "correctCount": row["correct_count"],
        "totalTimeMs": row["total_time_ms"],
        "questionResults": [],
    }


def get_overview(db, student_id: str) -> dict:
    submissions, attempts, audio = repo.fetch_overview(db, student_id, _OVERVIEW_AUDIO_LIMIT)
    return {
        "submissions": [_overview_submission(row) for row in submissions],
        "quizAttempts": [_overview_quiz_attempt(row) for row in attempts],
        "audioRecords": [row_to_audio_record(row) for row in audio],
    }


def list_students(db, role: str) -> list[dict]:
    # Test/synthetic accounts (is_test_account) are dev/QA fixtures, not real
    # students. A teacher's roster must never mix the two; admin tooling still
    # needs to see everything to debug the seeded data itself.
    exclude_test_accounts = role == "teacher"
    rows = repo.find_all(db, exclude_test_accounts)
    return [row_to_student(row) for row in rows]


def create_student(db, name: str, password: str) -> dict:
    name = name.strip()
    if not name:
        raise StudentServiceError(400, "Provide a student name.")
    auth.validate_password_policy(password)

    existing = repo.find_by_name_ci(db, name)
    if existing is not None:
        # Idempotent: re-adding a name already on the roster just hands
        # back its existing id instead of erroring, so a teacher can
        # re-submit the roster form without worrying about duplicates.
        return row_to_student(existing)

    student_id = str(uuid.uuid4())
    try:
        created = repo.insert(db, student_id, name, auth.hash_password(password))
    except UniqueViolation as exc:
        raise StudentServiceError(409, "Student already exists.") from exc
    return row_to_student(created)


def authenticate_student(
    db, student_id: Optional[str], name: Optional[str], password: str
) -> dict:
    """Verify credentials, silently upgrading a legacy password hash on
    success, and return the raw student row for the router to build a
    session from.
    """
    if student_id:
        row = repo.find_by_id(db, student_id)
    else:
        row = repo.find_by_name_ci(db, name.strip())

    if row is None:
        raise StudentServiceError(404, "Student not found")
    if row.get("status") != "active":
        raise StudentServiceError(403, "Student account is inactive")
    if row.get("password_reset_required"):
        raise StudentServiceError(403, "Student password reset required")

    valid, replacement_hash = auth.verify_password(row.get("password"), password)
    if not valid:
        raise StudentServiceError(401, "Wrong password")
    if replacement_hash is not None:
        repo.update_password_hash(db, row["id"], replacement_hash)

    return row


def reset_student_password(db, student_id: str, password: str) -> dict:
    auth.validate_password_policy(password)
    row = repo.reset_password(db, student_id, auth.hash_password(password))
    if row is None:
        raise StudentServiceError(404, "Student not found")
    return row_to_student(row)


def update_student(db, student_id: str, request) -> dict:
    set_clauses: list[str] = []
    params: list = []
    if request.name is not None:
        name = request.name.strip()
        if not name:
            raise StudentServiceError(400, "Provide a student name.")
        duplicate = repo.find_name_conflict(db, name, student_id)
        if duplicate is not None:
            raise StudentServiceError(409, "Student already exists.")
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
        raise StudentServiceError(400, "No student changes supplied.")

    try:
        row = repo.update_fields(db, student_id, set_clauses, params)
    except UniqueViolation as exc:
        raise StudentServiceError(409, "Student already exists.") from exc
    if row is None:
        raise StudentServiceError(404, "Student not found")
    return row_to_student(row)


def delete_student(db, student_id: str) -> None:
    if not delete_student_cascade(db, student_id):
        raise StudentServiceError(404, "Student not found")
