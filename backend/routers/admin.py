"""Admin console login.

Replaces the old client-side-only "admin123" check in AdminApp.tsx with a
real backend password check plus a signed JWT session cookie, matching the
student/teacher login pattern in auth.py. There is a single shared admin
account (no admin roster/table), so the JWT subject is a fixed constant.
"""
import os
import hmac

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel

import security.auth as auth
from db import (
    connect_db,
    row_to_student,
    row_to_teacher,
    row_to_custom_story,
    row_to_vocab_quiz_attempt,
)
from services.vocabulary_audio_import import (
    apply_vocabulary_audio_import,
    preview_vocabulary_audio_import,
)
from services.vocabulary_import import apply_vocabulary_import, preview_vocabulary_import

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Read after `import auth` above, which runs auth.py's own load_dotenv()
# calls as an import side effect - see the load-order note in auth.py.
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
ADMIN_SUBJECT_ID = "admin"


class AdminLoginRequest(BaseModel):
    password: str


@router.post("/login")
def login_admin(
    request: AdminLoginRequest,
    response: Response,
    http_request: Request,
):
    client_ip = http_request.client.host if http_request.client else "unknown"
    auth.check_login_rate_limit(f"admin:{client_ip}")
    if not ADMIN_PASSWORD:
        raise HTTPException(status_code=503, detail="Admin login is not configured.")
    if not hmac.compare_digest(request.password, ADMIN_PASSWORD):
        raise HTTPException(status_code=401, detail="Wrong password")
    token = auth.issue_token("admin", ADMIN_SUBJECT_ID)
    auth.set_session_cookie(response, token, "admin")
    return {"role": "admin"}


@router.post("/logout")
def logout_admin(response: Response):
    auth.clear_session_cookie(response, "admin")
    return {"loggedOut": True}


@router.get("/roster-overview")
def get_roster_overview(_identity: auth.Identity = Depends(auth.require_admin)):
    """One request for the admin console's landing data.

    The console previously fired three parallel calls (students, teachers,
    vocab-quiz-attempts) on every load/refresh — each its own auth check and
    pooled connection. Serving them from a single handler collapses that to
    one round-trip over one connection. Shapes are identical to the standalone
    ``/api/students``, ``/api/teachers`` and ``/api/vocab-quiz-attempts``
    (admin scope) endpoints, so the client stays field-for-field compatible.
    Quiz attempts keep their full ``questionResults`` payload — the IRT panel
    and the response-count metric both read per-question data.

    The three tables are independent (no join), so they are batched in a
    psycopg pipeline: the statements are sent together and the results read
    back after a single round-trip to Postgres, instead of three sequential
    query round-trips on the connection.
    """
    with connect_db() as db:
        with db.pipeline():
            students_cur = db.execute("SELECT * FROM students ORDER BY lower(name)")
            teachers_cur = db.execute("SELECT * FROM teachers ORDER BY lower(name)")
            attempts_cur = db.execute(
                "SELECT * FROM vocab_quiz_attempts ORDER BY completed_at DESC"
            )
        students = students_cur.fetchall()
        teachers = teachers_cur.fetchall()
        attempts = attempts_cur.fetchall()
    return {
        "students": [row_to_student(row) for row in students],
        "teachers": [row_to_teacher(row) for row in teachers],
        "quizAttempts": [row_to_vocab_quiz_attempt(row) for row in attempts],
    }


@router.get("/content-bank")
def get_content_bank(
    limit: int = Query(default=500, ge=1, le=500),
    skip: int = Query(default=0, ge=0),
    _identity: auth.Identity = Depends(auth.require_admin),
):
    """Return the admin-owned story and vocabulary source for Content Bank.

    Keep this separate from the student/teacher story reader so the admin
    console does not depend on the generic story-access policy when it reloads
    after an import.
    """
    with connect_db() as db:
        rows = db.execute(
            "SELECT * FROM custom_stories ORDER BY created_at DESC LIMIT %s OFFSET %s",
            (limit, skip),
        ).fetchall()
    return [row_to_custom_story(row) for row in rows]


@router.post("/vocabulary-import/preview")
async def preview_vocabulary_import_upload(
    file: UploadFile = File(...),
    _identity: auth.Identity = Depends(auth.require_admin),
):
    """Read-only: parse and validate an uploaded question-bank CSV/XLSX,
    report what an import would change. Writes nothing."""
    content = await file.read()
    try:
        with connect_db() as db:
            return preview_vocabulary_import(db, content, filename=file.filename or "")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/vocabulary-import/confirm")
async def confirm_vocabulary_import_upload(
    file: UploadFile = File(...),
    _identity: auth.Identity = Depends(auth.require_admin),
):
    """Re-validates the file from scratch and, only if it still passes,
    upserts each section's words into its matched story's vocab_assessment
    by wordId. Never trusts a client-held preview result."""
    content = await file.read()
    try:
        with connect_db() as db:
            return apply_vocabulary_import(db, content, filename=file.filename or "")
    except (ValueError, LookupError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/vocabulary-audio-import/preview")
async def preview_vocabulary_audio_import_upload(
    file: UploadFile = File(...),
    _identity: auth.Identity = Depends(auth.require_admin),
):
    """Read-only match report for a Word Key -> audio ZIP."""
    content = await file.read()
    try:
        with connect_db() as db:
            return preview_vocabulary_audio_import(db, content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/vocabulary-audio-import/confirm")
async def confirm_vocabulary_audio_import_upload(
    file: UploadFile = File(...),
    _identity: auth.Identity = Depends(auth.require_admin),
):
    """Re-validate and attach each matched audio file to all three rounds."""
    content = await file.read()
    try:
        with connect_db() as db:
            return apply_vocabulary_audio_import(db, content)
    except (ValueError, LookupError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
