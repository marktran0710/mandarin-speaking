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
