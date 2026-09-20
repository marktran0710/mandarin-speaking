import logging
import os

from fastapi import APIRouter, HTTPException

from config import settings
from db import connect_db

logger = logging.getLogger("speaking_app")

router = APIRouter()


@router.get("/health")
def health_check():
    """Liveness endpoint with explicit database and upload-storage status.

    Keep this endpoint HTTP-200 so dashboards can inspect a degraded service;
    deployment platforms should use ``/health/ready`` when they need a strict
    readiness signal.
    """
    db_ok = False
    try:
        with connect_db() as db:
            db.execute("SELECT 1").fetchone()
        db_ok = True
    except Exception as exc:
        logger.error("Health check DB failure: %s", exc)
    storage_ok = False
    try:
        os.makedirs(settings.upload_dir, exist_ok=True)
        probe_path = os.path.join(settings.upload_dir, f".write-probe-{os.getpid()}")
        with open(probe_path, "wb") as probe:
            probe.write(b"ok")
        os.unlink(probe_path)
        storage_ok = True
    except OSError as exc:
        logger.error("Health check upload-storage failure: %s", exc)
    return {
        "status": "ok" if db_ok and storage_ok else "degraded",
        "service": "Speaking App Backend",
        "database": "ok" if db_ok else "error",
        "storage": "ok" if storage_ok else "error",
    }


@router.get("/health/ready")
async def readiness_check():
    """Strict readiness probe used by deployment platforms."""
    result = health_check()
    if result["status"] != "ok":
        raise HTTPException(status_code=503, detail=result)
    return result
