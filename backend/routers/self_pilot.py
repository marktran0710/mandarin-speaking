"""Researcher self-pilot API — workflow rehearsal, not validation.

Wraps the canonical `infer_tone_attempt` so the researcher can run the whole
study workflow end to end and have every trial logged under data/self_pilot/.
The scientific path is identical to the study route; the only difference is
where the audio and the log rows land, and that every row is stamped
PILOT_ONLY / RESEARCHER_SELF_TEST.

Mounted only in study mode, alongside the canonical route.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pronunciation.wav2vec_tone.deployment_inference import (  # noqa: E402
    SCIENTIFIC_VERSION, ContractViolation, get_bundle, infer_tone_attempt,
    learner_response,
)
from pronunciation.wav2vec_tone.self_pilot import (  # noqa: E402
    AUDIO_DIR, CHALLENGE_PLAN, RUN_TECHNICAL, VALID_RUNS, append_trial,
    audio_filename, ensure_directories, load_items, next_trial_uid, read_trials,
)
from routers.tone_attempt import (  # noqa: E402
    TECHNICAL_FAILURE_CODES, TECHNICAL_MESSAGE,
)

logger = logging.getLogger("ompal.self_pilot")
router = APIRouter(prefix="/api/self-pilot", tags=["self-pilot"])


class SelfPilotResponse(BaseModel):
    """What the researcher's runner UI receives.

    Unlike the participant response this MAY carry the internal score: the
    researcher is the operator, not a study subject, and needs it to judge
    whether the system reacted plausibly. It is still absent from anything a
    participant would ever see.
    """

    trial_uid: str
    decision: str
    message: str
    technical_retry: bool
    # researcher-visible diagnostics
    raw_score_internal: float | None
    trajectory_available: bool
    failure_code: str
    latency_ms: float
    token_duration_ms: float | None


@router.get("/items")
async def self_pilot_items():
    """The 16 prompts, plus the fixed Run C plan."""
    items = load_items()
    return {
        "items": [{
            "item_id": item.item_id,
            "traditional_character": item.traditional_character,
            "expected_pinyin": item.expected_pinyin,
            "expected_tone": f"T{item.expected_tone}",
            "english_gloss": item.english_gloss,
            "teacher_approved": item.teacher_approved,
        } for item in items],
        "challenge_plan": list(CHALLENGE_PLAN),
        "runs": list(VALID_RUNS),
        "notice": ("These 16 items are awaiting teacher review. Using them here "
                   "is a technical rehearsal and does NOT constitute item "
                   "approval for the formal study."),
        "not_validation": ("Self-pilot data may never be used for accuracy, "
                           "PASS precision, agreement or kappa."),
    }


@router.get("/progress")
async def self_pilot_progress():
    """Descriptive counts only — deliberately no rates and no metrics."""
    trials = read_trials()
    per_run: dict[str, int] = {}
    for row in trials:
        per_run[row.get("run", "")] = per_run.get(row.get("run", ""), 0) + 1
    return {"total_trials": len(trials), "per_run": per_run,
            "PILOT_ONLY": True, "RESEARCHER_SELF_TEST": True}


@router.post("/attempt", response_model=SelfPilotResponse)
async def self_pilot_attempt(
    audio: UploadFile = File(...),
    item_id: str = Form(...),
    expected_tone: str = Form(default=""),
    run: str = Form(default=RUN_TECHNICAL),
    repetition: int = Form(default=1),
    capture_sample_rate: str = Form(default=""),
    pcm_spec_version: str = Form(default=""),
    challenge_type: str = Form(default=""),
    intended_manipulation: str = Form(default=""),
    researcher_notes: str = Form(default=""),
):
    """Score one self-pilot recording and log it under data/self_pilot/."""
    if run not in VALID_RUNS:
        raise HTTPException(status_code=400, detail=f"unknown run {run!r}")
    try:
        bundle = get_bundle()
    except ContractViolation as error:
        logger.error("refusing self-pilot inference: %s", error)
        raise HTTPException(status_code=503,
                            detail="pronunciation inference unavailable") from error

    ensure_directories()
    trial_uid = next_trial_uid()
    stored = AUDIO_DIR / audio_filename(trial_uid, run, item_id, repetition)
    payload = await audio.read()
    # Never overwrite: the uid makes each filename unique by construction.
    if stored.exists():
        raise HTTPException(status_code=409,
                            detail=f"refusing to overwrite {stored.name}")
    stored.write_bytes(payload)

    result = infer_tone_attempt(audio_path=stored, expected_tone=expected_tone,
                               item_id=item_id, bundle=bundle)
    visible = learner_response(result)
    technical = result["failure_code"] in TECHNICAL_FAILURE_CODES
    message = TECHNICAL_MESSAGE if technical else visible["message"]

    items = {item.item_id: item for item in load_items()}
    item = items.get(item_id)
    append_trial({
        "trial_uid": trial_uid, "run": run, "repetition": repetition,
        "item_id": item_id,
        "traditional_character": item.traditional_character if item else "",
        "expected_pinyin": item.expected_pinyin if item else "",
        "expected_tone": expected_tone,
        "audio_path": str(stored.relative_to(AUDIO_DIR.parent)).replace("\\", "/"),
        "capture_sample_rate": capture_sample_rate,
        "pcm_spec_version": pcm_spec_version,
        "source_sample_rate": result["source_sample_rate"],
        "token_duration_ms": result["token_duration_ms"],
        "trajectory_available": "YES" if result["trajectory_available"] else "NO",
        "raw_score_internal": ("" if result["raw_score"] is None
                               else f"{result['raw_score']:.6f}"),
        "system_decision": result["decision"],
        "decision_reason": result["decision_reason"],
        "failure_code": result["failure_code"],
        "latency_ms": f"{result['processing_latency_ms']:.2f}",
        "frontend_message": message,
        "technical_retry": "YES" if technical else "NO",
        "challenge_type": challenge_type,
        "intended_manipulation": intended_manipulation,
        "researcher_notes": researcher_notes,
        "scientific_version": result["scientific_version"],
        "deployment_version": result["deployment_version"],
        "audio_contract_version": result["audio_contract_version"],
        "fitted_model_sha256": result["fitted_model_sha256"],
    })

    return SelfPilotResponse(
        trial_uid=trial_uid,
        decision=visible["status"],
        message=message,
        technical_retry=technical,
        raw_score_internal=result["raw_score"],
        trajectory_available=result["trajectory_available"],
        failure_code=result["failure_code"],
        latency_ms=result["processing_latency_ms"],
        token_duration_ms=result["token_duration_ms"],
    )
