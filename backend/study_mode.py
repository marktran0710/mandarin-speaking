"""Study mode — one pronunciation engine, enforced at the HTTP boundary.

The app ships two pronunciation engines. `praat_analyzer` powers the story
recording analytics and emits a percentage `tone_accuracy`, a `detected_tone`
and produced-tone coaching text. The frozen OMPAL confirmer emits PASS/RETRY
and is forbidden from saying any of that.

Both are legitimate features, but a validation participant must never meet
both: the legacy output contradicts the frozen learner-output contract and
would contaminate the study. TV3 takes OPTION A — in a study build the legacy
scoring endpoints are disabled outright rather than rewired.

Off by default. `OMPAL_STUDY_MODE=1` turns it on, which:

  * blocks every legacy pronunciation-judgement route with 503
  * mounts the canonical /api/pronunciation/tone-attempt route

Normal application behaviour is untouched when the variable is unset.
"""

from __future__ import annotations

import os

from fastapi import Request
from fastapi.responses import JSONResponse

STUDY_MODE_ENV = "OMPAL_STUDY_MODE"

# Paths that can return a pronunciation judgement from the LEGACY engine.
# Prefix match. Keep this list exhaustive; a missed path is a live second
# engine, which is exactly what TV3 exists to prevent.
LEGACY_PRONUNCIATION_PATHS = (
    "/api/analyze",                 # covers /api/analyze and /api/analyze/stream
    "/api/benchmark/ompal",         # praat_analyzer-backed benchmark runner
)

DISABLED_PAYLOAD = {
    "detail": ("This endpoint is disabled in study mode. The controlled "
               "validation build exposes exactly one pronunciation engine, at "
               "/api/pronunciation/tone-attempt."),
    "study_mode": True,
}


def study_mode_enabled() -> bool:
    return os.getenv(STUDY_MODE_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def is_legacy_pronunciation_path(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix + "/")
               for prefix in LEGACY_PRONUNCIATION_PATHS)


async def study_mode_guard(request: Request, call_next):
    """Refuse legacy pronunciation routes whenever study mode is on."""
    if study_mode_enabled() and is_legacy_pronunciation_path(request.url.path):
        return JSONResponse(status_code=503, content=DISABLED_PAYLOAD)
    return await call_next(request)


def install(app) -> bool:
    """Attach the guard and, in study mode, mount the canonical route.

    Returns True when the study build is active. Safe to call unconditionally:
    with the variable unset it only registers a middleware that never fires.
    """
    app.middleware("http")(study_mode_guard)
    if not study_mode_enabled():
        return False

    from routers.self_pilot import router as self_pilot_router
    from routers.tone_attempt import router as tone_attempt_router

    app.include_router(tone_attempt_router)
    # Researcher workflow rehearsal. Same scientific path, separate namespace;
    # every row it writes is stamped PILOT_ONLY / RESEARCHER_SELF_TEST.
    app.include_router(self_pilot_router)
    return True
