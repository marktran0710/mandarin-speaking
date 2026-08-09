"""Production-equivalent HTTP surface for the frozen tone confirmer.

Deliberately NOT mounted in main.py. Registering this router is the act that
exposes the frozen system to users, and that must not happen until the human
validation gate clears. It exists so the real request path can be verified now.

The route is a thin shell: it decodes the upload to a temp file, calls
`infer_tone_attempt`, and returns `learner_response`. It contains no threshold,
no tone logic and no scoring. Everything scientific lives behind the single
canonical entry point.

To mount later:

    from pronunciation.wav2vec_tone.deployment_api import router
    app.include_router(router)
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi import APIRouter, File, Form, UploadFile  # noqa: E402

from pronunciation.wav2vec_tone.deployment_inference import (  # noqa: E402
    infer_tone_attempt, learner_response,
)

router = APIRouter(prefix="/api/tone-confirm", tags=["tone-confirmation"])

# Research logs are written by the caller, not returned to the client. The
# route keeps the last payload in memory only so tests can assert on it.
_LAST_RESEARCH_LOG: list[dict] = []


def last_research_log() -> dict | None:
    return _LAST_RESEARCH_LOG[-1] if _LAST_RESEARCH_LOG else None


@router.post("/attempt")
async def confirm_tone_attempt(
    audio: UploadFile = File(...),
    expected_tone: str = Form(...),
    item_id: str = Form(default=""),
):
    """Confirm one recorded attempt. Returns PASS/RETRY and nothing else.

    Every failure -- unreadable upload, wrong tone label, no trajectory --
    returns an ordinary RETRY. The client cannot distinguish a technical
    failure from a low-confidence attempt, which is exactly the frozen
    contract: RETRY means "not confirmed", never "wrong".
    """
    suffix = Path(audio.filename or "upload").suffix or ".bin"
    payload = await audio.read()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    try:
        result = infer_tone_attempt(
            audio_path=temporary,
            expected_tone=expected_tone,
            item_id=item_id or None,
        )
    finally:
        temporary.unlink(missing_ok=True)

    _LAST_RESEARCH_LOG.append(result)
    return learner_response(result)
