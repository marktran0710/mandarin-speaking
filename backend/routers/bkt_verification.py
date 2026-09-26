"""Admin-only, read-only BKT contract and evidence verification endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

import security.auth as auth
from db import connect_db
from services import bkt_verification_service as service


router = APIRouter(
    prefix="/api/admin/bkt-verification",
    tags=["admin-bkt-verification"],
    dependencies=[Depends(auth.require_admin)],
)


@router.get("")
def get_bkt_verification_bootstrap(_identity: auth.Identity = Depends(auth.require_admin)):
    with connect_db() as db:
        return service.get_bootstrap(db)


@router.get("/trace")
def get_bkt_verification_trace(
    student_id: str = Query(..., min_length=1),
    word_id: str | None = Query(default=None),
    _identity: auth.Identity = Depends(auth.require_admin),
):
    try:
        with connect_db() as db:
            return service.get_trace(db, student_id, word_id)
    except service.BktVerificationNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
