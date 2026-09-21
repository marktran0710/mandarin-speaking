"""Startup/shutdown event handlers, registered onto the app by app_factory.

Still uses FastAPI's @app.on_event-equivalent registration (app.add_event_
handler) rather than the newer `lifespan` context-manager parameter - a
pure relocation of the existing handlers, not a migration to the new API.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import anyio
from fastapi import FastAPI

from config import settings
from db import close_db, init_db, pool_max_size

logger = logging.getLogger("speaking_app")


async def startup_event() -> None:
    if os.getenv("APP_ENV", "development").lower() == "production":
        if os.getenv("COOKIE_SECURE", "false").lower() != "true":
            raise RuntimeError("COOKIE_SECURE=true is required in production.")
        if not os.getenv("ADMIN_PASSWORD", ""):
            raise RuntimeError("ADMIN_PASSWORD must be configured in production.")
        if not Path(settings.upload_dir).is_absolute() or not str(Path(settings.upload_dir)).startswith("/data"):
            raise RuntimeError("Production uploads must live on the persistent /data volume.")
    init_db()

    # DB-backed routes are plain `def`, so Starlette dispatches each to a
    # worker thread. Align the default thread limiter with the DB pool size so
    # we never run more concurrent blocking queries than the pool can serve -
    # extra threads would otherwise pile up waiting on connection checkout and
    # hit the pool timeout. ASR/Praat keep their own smaller semaphore on top.
    anyio.to_thread.current_default_thread_limiter().total_tokens = pool_max_size()


async def shutdown_database() -> None:
    close_db()


async def warm_vibevoice_asr() -> None:
    import services.asr as asr_service

    if asr_service.VIBEVOICE_WARM_ON_START:
        asr_service.ensure_vibevoice_load_started()


async def warm_ct_whisper() -> None:
    # Off by default: loading torch/transformers/librosa is only possible on
    # an image that installed requirements-local-asr.txt (the dev Docker
    # image), and even there it's ~2GB of extra memory + an 8s load a
    # deployment may not want to pay at every restart. Where it IS wanted,
    # this moves that ~8s cold-start cost off the first real student/teacher
    # request and onto server startup instead, in the background - it does
    # not delay /health/ready.
    import services.asr as asr_service

    if asr_service.CT_WHISPER_WARM_ON_START:
        logger.info("ctwhisper: CT_WHISPER_WARM_ON_START is set, kicking off background warm-up")
        asr_service.ensure_ct_whisper_load_started()


def register_lifespan_handlers(app: FastAPI) -> None:
    app.add_event_handler("startup", startup_event)
    app.add_event_handler("startup", warm_vibevoice_asr)
    app.add_event_handler("startup", warm_ct_whisper)
    app.add_event_handler("shutdown", shutdown_database)
