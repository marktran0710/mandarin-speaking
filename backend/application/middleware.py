"""HTTP middleware and the in-memory per-route rate limiter.

Registered on the app in this order (outermost first): GZip, CORS (both in
app_factory.py), security headers, then request timing - so timing measures
the whole request including the other two.
"""

from __future__ import annotations

import collections
import logging
import os
import threading
import time

from fastapi import HTTPException

logger = logging.getLogger("speaking_app")


async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), geolocation=(), payment=()")
    return response


# Per-request timing so the actually-slow endpoints show up in the logs (and in
# the browser's network panel via Server-Timing) instead of being guessed at.
# Requests at/above SLOW_REQUEST_MS are logged as warnings.
_SLOW_REQUEST_MS = float(os.getenv("SLOW_REQUEST_MS", "1000"))


async def log_request_timing(request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    response.headers["Server-Timing"] = f"app;dur={duration_ms:.1f}"
    if duration_ms >= _SLOW_REQUEST_MS:
        logger.warning(
            "slow request %s %s -> %s in %.0fms",
            request.method, request.url.path, response.status_code, duration_ms,
        )
    return response


# ── In-memory rate limiter ─────────────────────────────────────────────────
# Keyed by (route, client_ip). Tracks request timestamps in a deque.
_rate_limits: dict[str, collections.deque] = {}
_rate_limit_lock = threading.Lock()


def _check_rate_limit(key: str, max_requests: int, window_seconds: int) -> None:
    now = time.monotonic()
    with _rate_limit_lock:
        dq = _rate_limits.setdefault(key, collections.deque())
        # Drop timestamps outside the window
        while dq and now - dq[0] > window_seconds:
            dq.popleft()
        if len(dq) >= max_requests:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Max {max_requests} requests per {window_seconds}s.",
            )
        dq.append(now)
