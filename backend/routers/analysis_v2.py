"""Experimental character/phoneme/tone analysis API.

This router deliberately wraps the existing analysis pipeline instead of
changing it.  Stable V1 therefore keeps its request, response and scoring
behaviour while V2 adds an explicitly versioned character/phone projection.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from chinese_tones import detect_tone
import auth

router = APIRouter(dependencies=[Depends(auth.get_current_identity)])


def _main_module():
    # Imported lazily so unit tests can exercise the pure projection helpers
    # without triggering the application's router-import cycle.
    import main

    return main

ANALYSIS_VERSION = "phoneme_tone_v2"
SCHEMA_VERSION = "analysis_v2.character_phone.v2"
MODEL_VERSION = os.getenv("V2_ANALYSIS_MODEL_VERSION", "praat-character-projection.v1")


def _enabled() -> bool:
    return os.getenv("V2_ANALYSIS_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}


def _health_kpi_gate() -> dict[str, Any]:
    report_path = os.getenv("V2_KPI_REPORT", "").strip()
    if report_path:
        try:
            from pathlib import Path

            # Ignore an old offline report path if it is no longer available.
            json.loads(Path(report_path).read_text(encoding="utf-8"))
        except Exception:
            # A stale/malformed report must never unlock V2.
            pass
    configured = os.getenv("V2_KPI_STATUS", "NEEDS_DATA").strip().upper()
    if configured not in {"BLOCKED", "NEEDS_DATA", "PILOT_READY", "OWNER_PILOT_READY", "TEACHER_VALIDATED", "EXPERIMENTAL"}:
        configured = "NEEDS_DATA"
    status = "PASS" if configured in {"PILOT_READY", "OWNER_PILOT_READY", "TEACHER_VALIDATED"} else ("FAIL" if configured == "BLOCKED" else "NEEDS_DATA")
    release_status = "TEACHER_VALIDATED" if configured == "TEACHER_VALIDATED" else ("OWNER_PILOT_READY" if status == "PASS" else ("BLOCKED" if status == "FAIL" else "EXPERIMENTAL"))
    return {
        "status": status,
        "release_status": release_status,
        "passed": status == "PASS",
        "minimum_accuracy": 0.80,
        "character_alignment_success": 0.95,
        "audio_qc_auc": 0.80,
        "high_confidence_pass_precision": 0.92,
        "reason": "T5/neutral validation data and teacher validation are still required" if status != "PILOT_READY" else "Internal KPI thresholds passed; teacher validation remains required",
    }


def _pinyin_syllables(text: str, pinyin_hint: str = "") -> list[str]:
    # An explicit teacher/reference hint is part of the analysis contract
    # (including neutral-tone 5); generated readings still come from the
    # canonical backend service below.
    raw = pinyin_hint.strip() or ""
    if raw:
        return [part for part in re.split(r"[\s,]+", raw) if part]

    try:
        from pinyin_service import canonical_pinyin_tone3

        values = canonical_pinyin_tone3(text).split()
        if values:
            return [
                value
                for char, value in zip(text, values)
                if not char.isspace() and char not in "，。！？,.!?、"
            ]
    except Exception:
        pass

    return list(text)


def _tone_number(pinyin: str) -> int | None:
    match = re.search(r"([1-5])$", pinyin)
    return int(match.group(1)) if match else None


def _phone_tokens(pinyin: str) -> list[str]:
    base = re.sub(r"[1-5]$", "", pinyin.lower()).replace("ü", "v")
    # Keep common Mandarin initials intact before splitting the rime.
    initials = ("zh", "ch", "sh", "b", "p", "m", "f", "d", "t", "n", "l", "g", "k", "h", "j", "q", "x", "r", "z", "c", "s", "w", "y")
    for initial in initials:
        if base.startswith(initial) and len(base) > len(initial):
            return [initial, base[len(initial):]]
    return [base] if base else []


def _relative_probabilities(scores: Any) -> dict[str, float | None]:
    """Convert non-negative template similarities into relative evidence.

    ``detect_tone`` returns similarity scores, not calibrated likelihoods.  The
    previous V2 projection exposed those 0--100 scores under a
    ``tone_probabilities`` name, which was misleading to both the UI and
    offline exporters.  This function normalizes only model evidence and
    deliberately does not use the prompted/expected tone.  The result is
    marked as *uncalibrated* in the response; a held-out calibration set is
    still required before treating it as a real probability.
    """
    values: dict[str, float] = {}
    if isinstance(scores, dict):
        for key, value in scores.items():
            try:
                tone = int(key)
                score = float(value)
                if 1 <= tone <= 5 and math.isfinite(score) and score >= 0:
                    values[str(tone)] = score
            except (TypeError, ValueError):
                continue
    total = sum(values.values())
    result: dict[str, float | None] = {str(tone): None for tone in range(1, 6)}
    if total <= 0:
        return result
    for tone, score in values.items():
        result[tone] = round(score / total, 4)
    return result


def _clean_pitch_contour(contour: Any, start: float, end: float) -> list[tuple[float, float]]:
    """Return chronologically ordered, finite voiced pitch measurements."""
    points: list[tuple[float, float]] = []
    if not isinstance(contour, list):
        return points
    for point in contour:
        if not isinstance(point, (tuple, list)) or len(point) < 2:
            continue
        try:
            timestamp, frequency = float(point[0]), float(point[1])
        except (TypeError, ValueError):
            continue
        if math.isfinite(timestamp) and math.isfinite(frequency) and start <= timestamp <= end and frequency > 0:
            points.append((timestamp, frequency))
    return sorted(points, key=lambda point: point[0])


def _character_spans(
    start: float, end: float, count: int, contour: Any
) -> tuple[list[tuple[float, float]], str]:
    """Propose character spans, snapping proportional boundaries to voicing.

    Word alignment is supplied by the stable analyzer.  It does not yet expose
    per-character forced-alignment spans, so V2 must not pretend its phone
    boundaries are gold.  We improve the old equal-duration split only when
    the audio contains a nearby voiced-gap onset; otherwise the returned
    source explicitly remains ``duration_projection``.
    """
    if count <= 0 or end <= start:
        return [(start, start)] * max(count, 0), "unavailable"
    points = _clean_pitch_contour(contour, start, end)
    nominal = (end - start) / count
    boundaries = [start]
    source = "duration_projection"
    if len(points) >= 3:
        deltas = [points[index][0] - points[index - 1][0] for index in range(1, len(points))]
        positive_deltas = sorted(delta for delta in deltas if delta > 0)
        median_delta = positive_deltas[len(positive_deltas) // 2] if positive_deltas else 0.0
        # A gap substantially larger than the observed frame cadence is an
        # acoustic onset candidate.  The duration-based lower bound avoids
        # snapping to normal frame-to-frame jitter.
        gap_threshold = max(median_delta * 2.5, nominal * 0.12)
        onsets = [points[index][0] for index, delta in enumerate(deltas, start=1) if delta >= gap_threshold]
        for index in range(1, count):
            proposed = start + nominal * index
            nearby = [onset for onset in onsets if boundaries[-1] < onset < end]
            if nearby:
                candidate = min(nearby, key=lambda onset: abs(onset - proposed))
                if abs(candidate - proposed) <= nominal * 0.55:
                    boundaries.append(candidate)
                    source = "voicing_onset_refined_projection"
                    continue
            boundaries.append(proposed)
    else:
        boundaries.extend(start + nominal * index for index in range(1, count))
    boundaries.append(end)
    return list(zip(boundaries[:-1], boundaries[1:])), source


def _character_contour(contour: Any, character_index: int, character_count: int) -> list[Any]:
    """Return one contiguous time span of a word-level F0 contour.

    The legacy projection used ``contour[index::count]``.  That interleaves
    frames from every syllable, so a multi-character word gives each character
    the *entire* word's pitch movement.  In the absence of phone alignment we
    use equal-duration contiguous spans as a conservative fallback.  This is
    acoustic-only and does not use the expected tone or character identity.
    """
    if not isinstance(contour, list) or character_count <= 0:
        return []
    total = len(contour)
    start = round(total * character_index / character_count)
    end = round(total * (character_index + 1) / character_count)
    return contour[start:end]


def build_character_prosody(metrics: Any, transcription: str, pinyin_hint: str = "") -> list[dict[str, Any]]:
    """Project stable word spans into per-character and per-phone records.

    This is intentionally conservative: missing pitch produces ``Unknown``;
    neutral/T5 is never silently converted to an expected class.
    """
    text_chars = [char for char in transcription if not char.isspace() and not char in "，。！？,.!?、"]
    pinyin = _pinyin_syllables(transcription, pinyin_hint)
    words = getattr(metrics, "word_prosody", None) or []
    records: list[dict[str, Any]] = []
    char_cursor = 0
    for word in words:
        token = str(word.get("token", "")) if isinstance(word, dict) else ""
        syllables = word.get("syllables", []) if isinstance(word, dict) else []
        count = max(len(syllables), len([c for c in token if not c.isspace()]), 1)
        start = float(word.get("start_time", 0.0)) if isinstance(word, dict) else 0.0
        end = float(word.get("end_time", start)) if isinstance(word, dict) else start
        if not math.isfinite(start) or not math.isfinite(end) or end < start:
            start, end = 0.0, 0.0
        contour = word.get("pitch_contour", []) if isinstance(word, dict) else []
        confidence = float(word.get("confidence", 0.0) or 0.0) if isinstance(word, dict) else 0.0
        chars = [c for c in token if not c.isspace()] or text_chars[char_cursor:char_cursor + count]
        spans, boundary_source = _character_spans(start, end, count, contour)
        for offset in range(count):
            char = chars[offset] if offset < len(chars) else (text_chars[char_cursor] if char_cursor < len(text_chars) else "")
            pinyin_value = pinyin[char_cursor] if char_cursor < len(pinyin) else char
            expected = _tone_number(pinyin_value)
            c_start, c_end = spans[offset] if offset < len(spans) else (start, start)
            # Preserve the contiguous frame partition as a fallback for
            # legacy contours with malformed/non-monotonic timestamps.
            local_contour = [
                point for point in _clean_pitch_contour(contour, start, end)
                if c_start <= point[0] < c_end or (offset == count - 1 and point[0] == c_end)
            ]
            if not local_contour:
                local_contour = _character_contour(contour, offset, count)
            detected: int | None = None
            tone_scores: dict[str, float | None] = {str(tone): None for tone in range(1, 6)}
            tone_confidence = 0.0
            status = "unknown"
            if expected == 5:
                status = "neutral_model_unavailable"
            elif len(local_contour) >= 4:
                try:
                    detected_result = detect_tone(local_contour)
                    detected = detected_result.get("detected_tone")
                    tone_scores = _relative_probabilities(detected_result.get("scores"))
                    # This is a confidence in the available acoustic evidence,
                    # not a calibrated probability that the target was spoken.
                    # It intentionally never reads `expected`.
                    evidence = [value for value in tone_scores.values() if value is not None]
                    tone_confidence = (max(evidence) if evidence else 0.0) * min(1.0, len(local_contour) / 8.0)
                    status = "success"
                except Exception:
                    status = "unknown"
            elif expected != 5 and local_contour:
                status = "insufficient_voiced_pitch"
            phone_tokens = _phone_tokens(pinyin_value)
            phones = [
                {
                    "phone": phone,
                    "start_time": c_start + (c_end - c_start) * i / max(len(phone_tokens), 1),
                    "end_time": c_start + (c_end - c_start) * (i + 1) / max(len(phone_tokens), 1),
                    "boundary_source": "proportional_within_character",
                    "boundary_confidence": 0.0,
                }
                for i, phone in enumerate(phone_tokens)
            ]
            records.append({
                "char_index": char_cursor,
                "char": char,
                "pinyin": pinyin_value,
                "expected_tone": expected,
                "detected_tone": detected,
                "tone_status": status,
                "tone_probabilities": tone_scores,
                "tone_probability_status": "uncalibrated_relative_evidence",
                "tone_confidence": round(tone_confidence, 4),
                "start_time": round(c_start, 4),
                "end_time": round(c_end, 4),
                "alignment_confidence": round(confidence if boundary_source != "duration_projection" else 0.0, 4),
                "character_boundary_source": boundary_source,
                "phone_alignment_status": "not_acoustically_aligned",
                "phones": phones,
            })
            char_cursor += 1
    # If the legacy aligner returned no words, still expose a useful schema.
    while char_cursor < len(text_chars):
        char = text_chars[char_cursor]
        pinyin_value = pinyin[char_cursor] if char_cursor < len(pinyin) else char
        records.append({
            "char_index": char_cursor, "char": char, "pinyin": pinyin_value,
            "expected_tone": _tone_number(pinyin_value), "detected_tone": None,
            "tone_status": "unknown", "tone_probabilities": {str(t): None for t in range(1, 6)},
            "tone_probability_status": "unavailable", "tone_confidence": 0.0,
            "start_time": 0.0, "end_time": 0.0, "alignment_confidence": 0.0,
            "character_boundary_source": "unavailable",
            "phone_alignment_status": "not_acoustically_aligned",
            "phones": [
                {"phone": phone, "start_time": 0.0, "end_time": 0.0,
                 "boundary_source": "unavailable", "boundary_confidence": 0.0}
                for phone in _phone_tokens(pinyin_value)
            ],
        })
        char_cursor += 1
    return records


@router.get("/api/analyze/v2/health")
@router.get("/api/analysis-v2/health")
async def analysis_v2_health():
    return {
        "ready": _enabled(),
        "experimental": True,
        "analysis_version": ANALYSIS_VERSION,
        "analysis_schema_version": SCHEMA_VERSION,
        "model_version": MODEL_VERSION,
        "tone_classes": ["T1", "T2", "T3", "T4", "T5"],
        "t5_status": "needs_data",
        "deferred_requirements": ["T5 learner labels and sealed-test support"],
        "progression_eligible": False,
        "kpi_gate": _health_kpi_gate(),
    }


@router.post("/api/analyze/v2")
async def analyze_speech_v2(
    file: UploadFile = File(...),
    transcription: str = Form(""),
    asr_model: str = Form(""),
    scene_prompt: str = Form(""),
    scene_vocabulary: str = Form(""),
    ai_provider: str = Form(""),
    scene_image_url: str = Form(""),
    scene_phrases: str = Form(""),
    scene_suggested_answer: str = Form(""),
    scene_target_text: str = Form(""),
    scene_attempt_number: int = Form(1),
    verify_word: str = Form(""),
    pinyin_hint: str = Form(""),
    scene_reference_curves: str = Form(""),
    alignment_detail: str = Form("phoneme"),
    req: Request = None,
):
    if not _enabled():
        raise HTTPException(status_code=503, detail="Experimental V2 is not available")
    if not file:
        raise HTTPException(status_code=400, detail="No audio file provided")
    if req is not None:
        client_ip = req.client.host if req.client else "unknown"
        _main_module()._check_rate_limit(f"analyze-v2:{client_ip}", max_requests=30, window_seconds=60)
    content = await file.read()
    app_main = _main_module()
    if len(content) > app_main._MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio file too large")
    reference_word_curves = None
    if scene_reference_curves.strip():
        try:
            parsed = json.loads(scene_reference_curves)
            if isinstance(parsed, dict):
                reference_word_curves = {str(k): v for k, v in parsed.items() if isinstance(v, list) and v}
        except (json.JSONDecodeError, TypeError):
            reference_word_curves = None
    try:
        async def run_bounded_analysis():
            async with app_main.acquire_analysis_slot():
                return await app_main._do_analyze(
                    content, transcription, asr_model, scene_prompt, scene_vocabulary,
                    ai_provider, scene_image_url, scene_phrases, scene_suggested_answer,
                    scene_attempt_number, verify_word, pinyin_hint, reference_word_curves,
                    scene_target_text,
                )

        stable = await asyncio.wait_for(
            run_bounded_analysis(), timeout=app_main.ANALYZE_TIMEOUT_SECONDS
        )
        payload = stable.model_dump() if hasattr(stable, "model_dump") else stable.dict()
        payload.update({
            "analysis_version": ANALYSIS_VERSION,
            "analysis_schema_version": SCHEMA_VERSION,
            "model_version": MODEL_VERSION,
            "experimental": True,
            "progression_eligible": False,
            "alignment_detail": alignment_detail or "phoneme",
            "character_prosody": build_character_prosody(stable, stable.transcription or transcription, pinyin_hint),
            "neutral_tone_status": "needs_data",
            "kpi_gate": _health_kpi_gate(),
        })
        return payload
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Experimental analysis timed out") from exc
    except HTTPException:
        raise
    except Exception as exc:
        app_main.logger.exception("Error in experimental V2 analysis")
        raise HTTPException(status_code=500, detail=f"Experimental analysis failed: {exc}") from exc
