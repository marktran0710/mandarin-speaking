"""Admin-only, read-only metadata for the Learning Engine page (BKT, SRS, voice)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

import security.auth as auth
from services.learning_engine_service import get_learning_engine_metadata


router = APIRouter(
    tags=["admin-learning-engine"],
    dependencies=[Depends(auth.require_admin)],
)


@router.get("/api/admin/learning-engine")
def get_admin_learning_engine() -> dict:
    return get_learning_engine_metadata()
