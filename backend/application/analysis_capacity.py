"""Bounds how many /api/analyze requests run their CPU-bound stages (Praat,
local ASR) at once.

run_in_threadpool offloads this work off the event loop, but the threadpool
itself has no size limit tied to actual CPU capacity - a classroom of ~50
students recording around the same moment would otherwise spin up dozens of
CPU-heavy analyses simultaneously and thrash every core, making every single
one slower rather than a few finishing quickly in sequence. Extra requests
simply queue for a slot instead of being rejected; ANALYZE_TIMEOUT_SECONDS
still bounds how long any one request (including its queue wait) can take.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import HTTPException

from config import settings

ANALYZE_TIMEOUT_SECONDS = settings.analyze_timeout_seconds
ANALYZE_CONCURRENCY_LIMIT = settings.analyze_concurrency_limit
analyze_semaphore = asyncio.Semaphore(ANALYZE_CONCURRENCY_LIMIT)
ANALYZE_QUEUE_LIMIT = settings.analyze_queue_limit

_analysis_admission_lock = asyncio.Lock()
_analysis_waiters = 0


@asynccontextmanager
async def acquire_analysis_slot():
    """Admit a bounded number of CPU/ASR requests across all analysis routes."""
    global _analysis_waiters
    async with _analysis_admission_lock:
        if _analysis_waiters >= ANALYZE_QUEUE_LIMIT:
            raise HTTPException(
                status_code=503,
                detail="Analysis capacity is temporarily full. Please retry shortly.",
                headers={"Retry-After": "5"},
            )
        _analysis_waiters += 1

    counted_as_waiter = True
    try:
        async with analyze_semaphore:
            async with _analysis_admission_lock:
                _analysis_waiters -= 1
            counted_as_waiter = False
            yield
    finally:
        if counted_as_waiter:
            async with _analysis_admission_lock:
                _analysis_waiters -= 1
