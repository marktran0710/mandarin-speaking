"""Canonical pronunciation-assessment route for the controlled study.

This is the ONLY backend path that may return a tone judgement in a study
build. It is a shell: validate the request, hand it to the canonical
`infer_tone_attempt`, return the participant-visible fields. No threshold, no
tone logic, no scoring lives here.

Enabled only when study mode is on (`OMPAL_STUDY_MODE=1`), so that mounting it
is an explicit deployment act rather than a side effect of importing a module.
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pronunciation.wav2vec_tone.deployment_inference import (  # noqa: E402
    SCIENTIFIC_VERSION, ContractViolation, get_bundle, infer_tone_attempt,
    learner_response, validate_expected_tone,
)
import auth

logger = logging.getLogger("ompal.tone_attempt")
router = APIRouter(
    prefix="/api/pronunciation",
    tags=["tone-confirmation"],
    dependencies=[Depends(auth.get_current_identity)],
)

TECHNICAL_MESSAGE = "The recording could not be processed. Please record again."

# Failure codes that are the participant's recording going wrong rather than the
# model declining to confirm. Both return RETRY; only the wording differs, and
# neither implies a pronunciation error.
TECHNICAL_FAILURE_CODES = frozenset({
    "unreadable_audio", "empty_audio", "sample_rate_below_contract",
    "sample_rate_not_native", "invalid_expected_tone",
    "token_duration_out_of_contract", "alignment_failed",
    "alignment_span_missing", "unhandled_exception", "feature_schema_mismatch",
    "model_not_loaded", "artefact_hash_mismatch",
})


def study_mode_enabled() -> bool:
    return os.getenv("OMPAL_STUDY_MODE", "").strip() in ("1", "true", "TRUE", "yes")


class ToneAttemptResponse(BaseModel):
    """Everything a participant may receive. Nothing else is serialised."""

    decision: str
    message: str
    technical_retry: bool


@router.get("/tone-attempt/health")
async def tone_attempt_health():
    """Startup integrity, surfaced without exposing any scientific value."""
    try:
        bundle = get_bundle()
    except ContractViolation as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {
        "ready": True,
        "scientific_version": bundle.metadata["scientific_version"],
        "deployment_version": bundle.metadata["deployment_version"],
        "audio_contract_version": bundle.metadata["audio_contract_version"],
        "fitted_model_sha256": bundle.metadata["fitted_model_sha256"],
    }


@router.post("/tone-attempt", response_model=ToneAttemptResponse)
async def tone_attempt(
    audio: UploadFile = File(...),
    # Deliberately not `Form(...)`: a missing or empty tone must produce the
    # ordinary technical RETRY, not a 422 whose pydantic error body would leak
    # field paths and indices to a participant client.
    expected_tone: str = Form(default=""),
    item_id: str = Form(default=""),
    system_version: str = Form(default=SCIENTIFIC_VERSION),
    capture_sample_rate: str = Form(default=""),
    pcm_spec_version: str = Form(default=""),
):
    """Confirm one recorded attempt. Returns PASS or RETRY and nothing else.

    Fails closed: if the fitted-model bundle does not verify, the service
    refuses to answer rather than serving a prediction from an unknown artefact.
    """
    try:
        bundle = get_bundle()
    except ContractViolation as error:
        logger.error("refusing inference: %s", error)
        raise HTTPException(
            status_code=503,
            detail="pronunciation inference unavailable") from error

    if system_version and system_version != SCIENTIFIC_VERSION:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported system_version {system_version!r}")

    # Validate the tone before anything touches the audio, so an invalid label
    # can never reach feature construction.
    try:
        validate_expected_tone(expected_tone)
    except ValueError:
        return ToneAttemptResponse(decision="RETRY", message=TECHNICAL_MESSAGE,
                                   technical_retry=True)

    suffix = Path(audio.filename or "attempt").suffix or ".wav"
    payload = await audio.read()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    try:
        result = infer_tone_attempt(audio_path=temporary,
                                    expected_tone=expected_tone,
                                    item_id=item_id, bundle=bundle)
    finally:
        temporary.unlink(missing_ok=True)

    # Research log: server-side only. The score never enters the response model.
    logger.info("tone_attempt %s", {
        "item_id": item_id,
        "scientific_version": result["scientific_version"],
        "deployment_version": result["deployment_version"],
        "audio_contract_version": result["audio_contract_version"],
        "fitted_model_sha256": result["fitted_model_sha256"],
        "expected_tone": result["expected_tone"],
        "declared_capture_sample_rate": capture_sample_rate,
        "declared_pcm_spec_version": pcm_spec_version,
        "source_sample_rate": result["source_sample_rate"],
        "resampled": result["resampled"],
        "token_duration_ms": result["token_duration_ms"],
        "trajectory_available": result["trajectory_available"],
        "raw_score": result["raw_score"],
        "decision": result["decision"],
        "failure_code": result["failure_code"],
        "processing_latency_ms": result["processing_latency_ms"],
    })

    visible = learner_response(result)
    technical = result["failure_code"] in TECHNICAL_FAILURE_CODES
    return ToneAttemptResponse(
        decision=visible["status"],
        message=TECHNICAL_MESSAGE if technical else visible["message"],
        technical_retry=technical)
