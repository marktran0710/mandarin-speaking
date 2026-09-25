"""Admin console login.

Replaces the old client-side-only "admin123" check in AdminApp.tsx with a
real backend password check plus a signed JWT session cookie, matching the
student/teacher login pattern in auth.py. There is a single shared admin
account (no admin roster/table), so the JWT subject is a fixed constant.
"""
import os
import hmac

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel

import security.auth as auth
import services.admin_service as admin_service
from db import connect_db
from services.vocabulary_audio_import import (
    apply_vocabulary_audio_import,
    build_vocabulary_audio_sample,
    preview_vocabulary_audio_import,
)
from services.vocabulary_import import (
    apply_vocabulary_import,
    build_vocabulary_import_template,
    preview_vocabulary_import,
)

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
    """Return the admin landing data through the application service."""
    with connect_db() as db:
        return admin_service.get_roster_overview(db)


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
        return admin_service.list_content_bank(db, limit=limit, skip=skip)


@router.post("/vocabulary-import/preview")
async def preview_vocabulary_import_upload(
    file: UploadFile = File(...),
    mode: str = Form(...),
    _identity: auth.Identity = Depends(auth.require_admin),
):
    """Read-only: parse and validate an uploaded question-bank CSV/XLSX,
    report what an import would change. Writes nothing."""
    content = await file.read()
    try:
        with connect_db() as db:
            return preview_vocabulary_import(db, content, filename=file.filename or "", mode=mode)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/vocabulary-import/confirm")
async def confirm_vocabulary_import_upload(
    file: UploadFile = File(...),
    mode: str = Form(...),
    _identity: auth.Identity = Depends(auth.require_admin),
):
    """Re-validates the file from scratch and replaces each matched lesson's
    canonical vocab_assessment by Word Key. Never trusts a client-held preview
    result."""
    content = await file.read()
    try:
        with connect_db() as db:
            return apply_vocabulary_import(db, content, filename=file.filename or "", mode=mode)
    except (ValueError, LookupError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/vocabulary-import/template")
def download_vocabulary_import_template(
    _identity: auth.Identity = Depends(auth.require_admin),
):
    """Download the self-documenting canonical vocabulary XLSX template."""
    return Response(
        content=build_vocabulary_import_template(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="vocabulary-import-template.xlsx"'},
    )


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


@router.get("/vocabulary-audio-import/template")
def download_vocabulary_audio_template(
    _identity: auth.Identity = Depends(auth.require_admin),
):
    """Download a mapping-only ZIP showing the exact Word Key filename contract."""
    return Response(
        content=build_vocabulary_audio_sample(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="vocabulary-audio-sample.zip"'},
    )


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
