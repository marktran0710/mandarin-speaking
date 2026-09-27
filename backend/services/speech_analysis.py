"""The central speech-analysis orchestration: given one recording, run
ASR, Praat acoustic analysis, content verification, pronunciation scoring,
and AI feedback together and assemble the combined AnalysisResponse.

This module composes the other services/* domains (asr, content_verification,
pronunciation_scoring, ai_feedback, media, text_normalization) plus the
dedicated grading modules (praat_analyzer, chinese_tones, tone_decision,
reached indirectly through analyze_all) into one request-level use case. It
does not itself decide what a "correct" tone or pronunciation looks like —
that logic stays in the modules it calls.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from statistics import median
from typing import Any, Callable, Dict, Optional

from starlette.concurrency import run_in_threadpool

import helpers.caf_metrics as caf_metrics
from helpers.pinyin_service import canonical_pinyin
from api.schemas.models import AnalysisResponse, ProcessingTrace, ProcessingTraceStage
from domain.speech.acoustics import analyze_all, extract_pitch
from services.asr import transcribe_audio_content
from services.content.verification import (
    assess_recording_quality,
    _target_syllable_count,
    _scene_content_match,
    _scene_content_diff,
    _acoustic_scoring_source,
    _missing_scene_content_units,
    finalize_feedback_quality,
    _verify_word_transcription,
    build_analysis_description,
)
from services.media import resolve_image_b64
from services.ai_feedback import AI_FEEDBACK_PROVIDER, generate_language_feedback
from services.pronunciation_scoring import (
    apply_recording_qc_to_diagnostics,
    build_pronunciation_mastery,
    classify_vowel_quality,
    build_tone_direction,
)

_PITCH_PROFILE_VERSION = "pitch-profile-comparison-v1"
_PRIMARY_PITCH_RANGE_HZ = (75, 500)
_PITCH_PROFILE_RANGES = {
    "male": (75, 300),
    "female": (100, 500),
}


def _measure_pitch_profile_comparison(
    audio_path: str,
    snapshot: Optional[Dict[str, str]],
) -> Optional[dict]:
    """Measure an additive pitch profile without touching scoring evidence."""
    if not snapshot or snapshot.get("voice_hint_mode") != "avatar":
        return None
    suggestion = snapshot.get("student_mascot")
    comparison_range = _PITCH_PROFILE_RANGES.get(suggestion or "")
    if comparison_range is None:
        return {
            "config_version": _PITCH_PROFILE_VERSION,
            "suggestion": suggestion,
            "primary_range_hz": list(_PRIMARY_PITCH_RANGE_HZ),
            "comparison_range_hz": None,
            "contour": [],
            "voiced_frame_count": 0,
            "median_f0_hz": None,
            "status": "invalid_profile",
            "appliedToScoring": False,
        }

    try:
        contour = extract_pitch(
            audio_path,
            pitch_floor=comparison_range[0],
            pitch_ceiling=comparison_range[1],
        )
        frequencies = [frequency for _, frequency in contour if frequency > 0]
        return {
            "config_version": _PITCH_PROFILE_VERSION,
            "suggestion": suggestion,
            "primary_range_hz": list(_PRIMARY_PITCH_RANGE_HZ),
            "comparison_range_hz": list(comparison_range),
            "contour": contour,
            "voiced_frame_count": len(frequencies),
            "median_f0_hz": float(median(frequencies)) if frequencies else None,
            "status": "measured" if frequencies else "no_voiced_frames",
            "appliedToScoring": False,
        }
    except Exception as exc:
        return {
            "config_version": _PITCH_PROFILE_VERSION,
            "suggestion": suggestion,
            "primary_range_hz": list(_PRIMARY_PITCH_RANGE_HZ),
            "comparison_range_hz": list(comparison_range),
            "contour": [],
            "voiced_frame_count": 0,
            "median_f0_hz": None,
            "status": "failed",
            "error": str(exc),
            "appliedToScoring": False,
        }
async def _do_analyze(
    content: bytes,
    transcription: str,
    asr_model: str,
    scene_prompt: str = "",
    scene_vocabulary: str = "",
    ai_provider: str = "",
    scene_image_url: str = "",
    scene_phrases: str = "",
    scene_suggested_answer: str = "",
    scene_attempt_number: int = 1,
    verify_word: str = "",
    pinyin_hint: str = "",
    reference_word_curves: Optional[Dict[str, list]] = None,
    scene_target_text: str = "",
    on_stage: Optional[Callable[[dict], None]] = None,
    # Optional attempt identity fields are retained for backward-compatible
    # clients; they do not enable a separate research or scoring path.
    participant_id: str = "",
    item_id: str = "",
    session_id: str = "",
    attempt_id: str = "",
    attempt_number: int = 1,
    attempt_type: str = "WHOLE_SENTENCE_INITIAL",
    study_phase: str = "",
    pitch_profile_snapshot: Optional[Dict[str, str]] = None,
) -> AnalysisResponse:
    tmp_path = None
    trace_started_at = time.perf_counter()
    trace_entries: list[dict[str, Any]] = []

    def add_trace_stage(
        stage: str,
        status: str,
        started_at: float,
        *,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        detail: Optional[str] = None,
        reason_codes: Optional[list[str]] = None,
        input: Optional[Dict[str, Any]] = None,
        output: Optional[Dict[str, Any]] = None,
    ) -> None:
        entry = {
            "stage": stage,
            "status": status,
            "duration_ms": round((time.perf_counter() - started_at) * 1000, 1),
            "model": model,
            "provider": provider,
            "detail": detail,
            "reason_codes": reason_codes or [],
            "input": input,
            "output": output,
        }
        trace_entries.append(entry)
        if on_stage is not None:
            on_stage(entry)

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
            tmp_file.write(content)
            tmp_path = tmp_file.name

        preflight_started_at = time.perf_counter()
        quality_target = verify_word.strip() or scene_target_text.strip() or scene_suggested_answer.strip()
        recording_preflight = assess_recording_quality(
            content,
            expected_syllable_count=_target_syllable_count(quality_target),
        )
        add_trace_stage(
            "preflight",
            recording_preflight.get("status", "review"),
            preflight_started_at,
            detail=recording_preflight.get("student_message") or recording_preflight.get("reason"),
            reason_codes=recording_preflight.get("reason_codes"),
            input={"audio_bytes": len(content)},
            output=recording_preflight,
        )
        transcription_model = ""
        ai_feedback = None
        image_b64, image_mime = await resolve_image_b64(scene_image_url) or (None, "")

        asr_started_at = time.perf_counter()
        sentence_target = scene_target_text.strip() or scene_suggested_answer.strip()

        # Scene vocabulary phrases arrive "; "-joined (see StoryRecorder.tsx)
        # since a scene can teach more than one multi-word phrase (e.g.
        # "這個週末; 做什麼"); split back out for the phrase-context rescue.
        target_phrases = [p.strip() for p in scene_phrases.split(";") if p.strip()]

        def _run_praat(path: str, tx: str, tx_pinyin_hint: str):
            return analyze_all(
                path, tx, pinyin_hint=tx_pinyin_hint,
                reference_word_curves=reference_word_curves,
                target_phrases=target_phrases,
            )

        # Whole-sentence practice with a known target sentence is the one case
        # where Praat's scoring text is knowable before ASR resolves:
        # _acoustic_scoring_source (below) only falls back to the raw ASR
        # transcript on a *confirmed* mismatch (scene_content_match is False),
        # and that can't be known before ASR runs anyway — so the common case
        # (no mismatch) always ends up scoring against sentence_target
        # regardless of what ASR returns. Start Praat against sentence_target
        # CONCURRENTLY with the ASR call below instead of sequentially after
        # it; only the rare confirmed-mismatch branch further down pays for a
        # second Praat pass, against the real transcript, same as before.
        speculative_pinyin_hint = (pinyin_hint.strip() or canonical_pinyin(sentence_target)) if sentence_target else ""
        can_speculate_scene_target = (
            bool(sentence_target)
            and not verify_word.strip()
            and not transcription.strip()
        )
        speculative_praat_started_at = time.perf_counter()
        speculative_praat_task = (
            asyncio.create_task(run_in_threadpool(_run_praat, tmp_path, sentence_target, speculative_pinyin_hint))
            if can_speculate_scene_target
            else None
        )

        if not transcription.strip():
            selected_asr_model = asr_model.strip() or "auto"
            try:
                transcription_result = await transcribe_audio_content(
                    content, selected_asr_model, vocab_hint=scene_vocabulary
                )
                transcription = transcription_result.text
                transcription_model = transcription_result.model
                add_trace_stage(
                    "asr",
                    "passed" if transcription.strip() else "review",
                    asr_started_at,
                    model=transcription_model,
                    detail="Backend transcription completed." if transcription.strip() else "ASR returned no transcript.",
                    input={"asr_model": selected_asr_model, "scene_vocabulary": scene_vocabulary},
                    output={"transcription": transcription, "model": transcription_model},
                )
            except Exception as exc:
                if speculative_praat_task is not None:
                    # A thread already running Praat can't actually be
                    # interrupted — let it finish naturally and retrieve its
                    # result/exception so it isn't reported as never collected.
                    speculative_praat_task.add_done_callback(lambda t: t.exception())
                    speculative_praat_task = None
                add_trace_stage(
                    "asr", "failed", asr_started_at, model=selected_asr_model, detail=str(exc),
                    input={"asr_model": selected_asr_model, "scene_vocabulary": scene_vocabulary},
                )
                raise
        elif not trace_entries or trace_entries[-1]["stage"] != "asr":
            add_trace_stage(
                "asr",
                "skipped",
                asr_started_at,
                model=transcription_model or None,
                detail="Transcript was supplied by the caller.",
                input={"note": "Transcript was supplied by the caller, not transcribed."},
                output={"transcription": transcription, "model": transcription_model or None},
            )

        sentence_content_verified = bool(asr_model.strip() or transcription_model.strip())
        scene_content_match = None
        if (
            sentence_target
            and not verify_word.strip()
            and transcription.strip()
            and sentence_content_verified
        ):
            scene_content_match = _scene_content_match(sentence_target, transcription)

        # Use the known scene sentence for acoustic scoring unless the ASR
        # content check came back with a confirmed mismatch. See
        # _acoustic_scoring_source's docstring for why an unverified (None)
        # result must not fall back to the raw ASR transcript the same way a
        # real mismatch does — that used to silently cut the measured
        # syllable count for a correctly-spoken attempt.
        scoring_source = _acoustic_scoring_source(sentence_target, scene_content_match)
        if scoring_source == "scene_target":
            scoring_transcription = sentence_target
            scoring_pinyin_hint = speculative_pinyin_hint or (pinyin_hint.strip() or canonical_pinyin(sentence_target))
        else:
            scoring_transcription = transcription
            scoring_pinyin_hint = (
                pinyin_hint.strip()
                if pinyin_hint.strip() and not sentence_target
                else canonical_pinyin(transcription)
            )
            if speculative_praat_task is not None:
                # The speculative pass (above) scored sentence_target, but a
                # confirmed mismatch means that text is now known to be wrong —
                # discard it the same way as the ASR-failure branch above, and
                # score fresh against the real transcript below.
                speculative_praat_task.add_done_callback(lambda t: t.exception())
                speculative_praat_task = None

        # Run Praat (CPU-bound, threadpool) and optional word-content
        # verification together. Coaching is deliberately deferred until
        # Praat and the recording-quality gate have finalized their evidence.
        verify_coro = (
            _verify_word_transcription(content, verify_word, vocab_hint=scene_vocabulary)
            if verify_word.strip()
            else asyncio.sleep(0, result=(None, None))
        )
        praat_input = {
            "pinyin_hint": scoring_pinyin_hint or None,
            "scoring_text": scoring_transcription,
            "scoring_source": scoring_source,
            "reference_word_curves_provided": bool(reference_word_curves),
            "target_phrases": target_phrases or None,
        }

        async def run_praat_stage():
            started_at = speculative_praat_started_at if speculative_praat_task is not None else time.perf_counter()
            try:
                if speculative_praat_task is not None:
                    result = await speculative_praat_task
                else:
                    result = await run_in_threadpool(_run_praat, tmp_path, scoring_transcription, scoring_pinyin_hint)
            except Exception as exc:
                add_trace_stage("praat", "failed", started_at, detail=str(exc), input=praat_input)
                raise
            (r_pitch_contour, r_formants, r_speech_rate, r_fluency_score, r_pitch_stats,
             r_word_prosody, r_detected_tone, r_tone_accuracy, _r_feedback,
             r_pause_analysis) = result
            add_trace_stage(
                "praat", "passed", started_at, detail="Acoustic analysis completed.",
                input=praat_input,
                output={
                    "pitch_contour": r_pitch_contour,
                    "formants": r_formants,
                    "speech_rate": r_speech_rate,
                    "fluency_score": r_fluency_score,
                    "pitch_statistics": r_pitch_stats,
                    "word_prosody": r_word_prosody,
                    "detected_tone": r_detected_tone,
                    "tone_accuracy": r_tone_accuracy,
                    "pause_analysis": r_pause_analysis,
                },
            )
            return result

        async def run_verify_stage():
            started_at = time.perf_counter()
            result = await verify_coro
            if verify_word.strip():
                add_trace_stage(
                    "content_verification", "passed", started_at,
                    detail="Independent word verification completed.",
                    input={"verify_word": verify_word},
                    output={"recognized_text": result[0], "content_match": result[1]},
                )
            return result

        (praat_result, (recognized_text, content_match)) = await asyncio.gather(
            run_praat_stage(),
            run_verify_stage(),
        )
        ai_feedback = None
        if sentence_target and not verify_word.strip():
            content_match = scene_content_match
            recognized_text = (transcription or None) if sentence_content_verified else None
            verification_started_at = time.perf_counter()
            add_trace_stage(
                "content_verification",
                "passed" if content_match is True else "review",
                verification_started_at,
                detail="Independent sentence ASR was compared with the scene target.",
                input={"target_text": sentence_target},
                output={
                    "recognized_text": recognized_text,
                    "content_match": content_match,
                    "asr_model": transcription_model or asr_model or None,
                },
            )
        content_target = verify_word.strip() or sentence_target
        recognized_for_diff = (
            recognized_text
            if verify_word.strip()
            else (transcription if sentence_content_verified else "")
        )
        content_diff = _scene_content_diff(content_target, recognized_for_diff or "")
        (pitch_contour, formants, speech_rate, fluency_score, pitch_stats,
         word_prosody, detected_tone, tone_accuracy, feedback,
         pause_analysis) = praat_result

        # No speech → noise from the mic can spuriously match a tone reference
        quality_started_at = time.perf_counter()
        feedback_quality = finalize_feedback_quality(
            recording_preflight,
            pitch_contour,
            transcription,
            content_match=content_match,
            content_was_verified=bool(verify_word.strip()) or sentence_content_verified,
        )
        add_trace_stage(
            "quality_gate",
            "passed" if feedback_quality["can_score_pronunciation"] else "retry",
            quality_started_at,
            detail=feedback_quality.get("student_message") or "Quality gate evaluated.",
            reason_codes=feedback_quality.get("reason_codes"),
            input={
                "preflight_status": recording_preflight.get("status"),
                "content_was_verified": bool(verify_word.strip()) or sentence_content_verified,
            },
            output=feedback_quality,
        )

        if not feedback_quality["can_score_pronunciation"]:
            tone_accuracy = 0
            detected_tone = 0
            fluency_score = 0.0
            feedback = feedback_quality["student_message"]
            for word in word_prosody:
                word["judged"] = False
                word["tone_accuracy"] = 0.0
                word["shape_accuracy"] = 0.0
                word["passed"] = None
                word["feedback"] = feedback_quality["student_message"]
                for syllable in word.get("syllables") or []:
                    syllable["score"] = 0.0
                    syllable["passed"] = None

        vowel_quality = classify_vowel_quality(formants)
        tone_direction = build_tone_direction(pitch_contour, detected_tone, tone_accuracy)

        # Turn the raw pause/rate measurements into judged, story-aggregatable
        # signals: how many pauses landed at a natural clause/punctuation
        # boundary in the reference script vs. mid-phrase ("choppy"), and the
        # articulation rate (syllables/sec, pauses excluded) for speed
        # feedback. Merged into pause_analysis so the frontend can pick these
        # up the same way it already reads pause_count/longest_pause.
        character_count = sum(1 for ch in scoring_transcription if "一" <= ch <= "鿿")
        fluency_for_response = caf_metrics.fluency_metrics(
            speech_rate, pause_analysis, character_count
        )
        # The teacher's listen script is the authoritative phrase-break source;
        # fall back to the suggested answer only for older scenes that have no
        # dedicated listen script.
        pause_reference_text = (
            scene_target_text.strip()
            or scene_suggested_answer.strip()
            or transcription
        )
        pause_judgment = caf_metrics.classify_pauses(
            pause_reference_text, pause_analysis, word_prosody
        )
        pause_analysis = {
            **pause_analysis,
            "articulation_rate": fluency_for_response["articulation_rate"],
            "choppy_pause_count": len(pause_judgment["choppy"]) if pause_judgment["judged"] else 0,
            "natural_pause_count": len(pause_judgment["natural"]) if pause_judgment["judged"] else 0,
        }

        feedback_started_at = time.perf_counter()
        feedback_timeout = False
        if feedback_quality["can_score_pronunciation"]:
            try:
                ai_feedback = await asyncio.wait_for(
                    generate_language_feedback(
                        transcription, scene_prompt, scene_vocabulary,
                        praat_tone_accuracy=float(tone_accuracy),
                        praat_fluency_score=float(fluency_score),
                        praat_vowel_quality=vowel_quality or "",
                        praat_pause_analysis=pause_analysis,
                        praat_speech_rate=float(speech_rate),
                        word_prosody=word_prosody,
                        provider=ai_provider or None,
                        image_b64=image_b64, image_mime=image_mime,
                        scene_phrases=scene_phrases,
                        scene_suggested_answer=scene_suggested_answer,
                        scene_attempt_number=scene_attempt_number,
                    ),
                    timeout=30.0,
                )
                provenance = ai_feedback.get("feedback_provenance", {})
                add_trace_stage(
                    "feedback",
                    "passed",
                    feedback_started_at,
                    provider=provenance.get("executed_provider") or ai_feedback.get("provider"),
                    detail="Coaching completed from finalized Praat evidence.",
                    input={
                        "requested_provider": ai_provider or "backend-default",
                        "tone_accuracy": float(tone_accuracy),
                        "fluency_score": float(fluency_score),
                        "speech_rate": float(speech_rate),
                        "vowel_quality": vowel_quality or None,
                        "pause_analysis": pause_analysis,
                        "word_prosody": word_prosody,
                    },
                    output={"feedback_provenance": provenance},
                )
            except TimeoutError:
                feedback_timeout = True
                add_trace_stage(
                    "feedback",
                    "failed",
                    feedback_started_at,
                    provider=ai_provider or "backend-default",
                    detail="Cloud coaching exceeded the 30-second evidence-grounding budget; local feedback was used.",
                    reason_codes=["feedback_timeout"],
                )
        else:
            add_trace_stage(
                "feedback",
                "skipped",
                feedback_started_at,
                provider=ai_provider or "backend-default",
                detail="Recording evidence was not reliable enough for coaching.",
                reason_codes=feedback_quality.get("reason_codes"),
            )

        # The deterministic local note remains authoritative for
        # pronunciation; cloud AI uses the measurements for coaching but does
        # not decide the student's score or verdict.
        from services.ai_feedback import (
            apply_feedback_quality_gate as _apply_feedback_quality_gate,
            fallback_language_feedback as _local_fb,
        )
        local_fb = _local_fb(
            transcription, scene_prompt, scene_vocabulary,
            praat_tone_accuracy=float(tone_accuracy),
            praat_fluency_score=float(fluency_score),
            praat_vowel_quality=vowel_quality or "",
            praat_pause_analysis=pause_analysis,
            praat_speech_rate=float(speech_rate),
            word_prosody=word_prosody,
            image_b64=image_b64,
            scene_phrases=scene_phrases,
            scene_suggested_answer=scene_suggested_answer,
            scene_attempt_number=scene_attempt_number,
        )
        if isinstance(ai_feedback, dict):
            if ai_feedback.get("provider") == "local":
                ai_feedback = local_fb
            else:
                ai_feedback["pronunciation_note"] = local_fb["pronunciation_note"]
        else:
            ai_feedback = local_fb
        if not isinstance(ai_feedback.get("feedback_provenance") if isinstance(ai_feedback, dict) else None, dict):
            requested_provider = (ai_provider or AI_FEEDBACK_PROVIDER or "local").strip().lower()
            acoustic_context_used = bool(feedback_quality["can_score_pronunciation"])
            ai_feedback["feedback_provenance"] = {
                "requested_provider": requested_provider,
                "executed_provider": "local",
                "fallback_used": feedback_timeout or requested_provider != "local",
                "fallback_reason": (
                    "feedback_timeout"
                    if feedback_timeout
                    else "recording_not_scorable"
                    if not acoustic_context_used
                    else None
                ),
                "acoustic_context_used": acoustic_context_used,
                "acoustic_context_supplied": acoustic_context_used,
                "pronunciation_source": (
                    "praat_acoustic_measurements"
                    if acoustic_context_used
                    else "local_deterministic"
                ),
            }
        ai_feedback = _apply_feedback_quality_gate(
            ai_feedback,
            feedback_quality,
            transcription=transcription,
            scene_vocabulary=scene_vocabulary,
        )
        description = build_analysis_description(scoring_transcription, transcription_model, word_prosody)

        # Recording-level QC is a gate on the *diagnostic* layer: when the
        # recording itself cannot support a judgement, no per-syllable verdict
        # may stand, however the contour happened to score. This deliberately
        # does not touch word_prosody[].passed — progression keeps running on
        # the legacy path exactly as before this patch.
        tone_diagnostics = apply_recording_qc_to_diagnostics(
            word_prosody, feedback_quality
        )
        pronunciation_mastery = build_pronunciation_mastery(
            word_prosody,
            feedback_quality,
            content_match=content_match,
            content_check_requested=bool(content_target),
            missing_target_units=(
                _missing_scene_content_units(content_target, recognized_for_diff or "")
                if content_match is False
                else []
            ),
        )

        # The optional research feedback layer is intentionally absent from
        # the classroom build. Keep the response field for compatibility with
        # older clients, but never compute or persist research-only data.
        assistive_feedback_result = None
        pitch_profile_comparison = await run_in_threadpool(
            _measure_pitch_profile_comparison, tmp_path, pitch_profile_snapshot
        )

        return AnalysisResponse(
            description=description,
            transcription=transcription,
            transcription_model=transcription_model,
            pitch_contour=pitch_contour,
            word_prosody=word_prosody,
            detected_tone=detected_tone,
            tone_accuracy=tone_accuracy,
            formants=formants,
            vowel_quality=vowel_quality,
            speech_rate=speech_rate,
            fluency_score=fluency_score,
            pitch_statistics=pitch_stats,
            pitch_profile_comparison=pitch_profile_comparison,
            tone_direction=tone_direction,
            pause_analysis=pause_analysis,
            feedback=feedback,
            ai_feedback=ai_feedback,
            feedback_provenance=ai_feedback.get("feedback_provenance", {}),
            recognized_text=recognized_text,
            content_match=content_match,
            content_diff=content_diff,
            feedback_quality=feedback_quality,
            tone_diagnostics=tone_diagnostics,
            pronunciation_mastery=pronunciation_mastery,
            assistive_feedback=assistive_feedback_result,
            processing_trace=ProcessingTrace(
                stages=[ProcessingTraceStage(**entry) for entry in trace_entries],
                total_duration_ms=round((time.perf_counter() - trace_started_at) * 1000, 1),
            ),
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
