import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

import security.auth as auth
import services.help_request_service as help_request_service
from db import connect_db
from main import HelpRequest

router = APIRouter()


@router.get("/api/help-requests")
def list_help_requests(
    limit: int = Query(default=100, ge=1, le=500),
    skip: int = Query(default=0, ge=0),
    identity: auth.Identity = Depends(auth.require_teacher_or_admin),
):
    with connect_db() as db:
        return help_request_service.list_help_requests(db, limit, skip)


@router.post("/api/help-requests")
def create_help_request(
    request: HelpRequest,
    identity: auth.Identity = Depends(auth.require_student),
):
    with connect_db() as db:
        return help_request_service.create_help_request(db, request)


@router.post("/api/help-requests/{request_id}/resolve")
def resolve_help_request(
    request_id: str,
    identity: auth.Identity = Depends(auth.require_teacher_or_admin),
):
    resolved_at = datetime.datetime.utcnow().isoformat() + "Z"
    with connect_db() as db:
        try:
            return help_request_service.resolve_help_request(db, request_id, resolved_at)
        except help_request_service.HelpRequestServiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
