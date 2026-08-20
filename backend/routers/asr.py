import asyncio
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from ai_feedback import available_providers, default_provider
import auth
import main
from main import AnalysisResponse, AsrStatusResponse, TranscriptionResponse

router = APIRouter(dependencies=[Depends(auth.get_current_identity)])


def _sse_line(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@router.get("/api/asr-status", response_model=AsrStatusResponse)
async def get_asr_status():
    with main._vibevoice_load_lock:
        if main._vibevoice_asr_model is not None:
            return AsrStatusResponse(
                provider="vibevoice",
                status="ready",
                message="VibeVoice-ASR is ready.",
            )
        if main._vibevoice_load_error:
            return AsrStatusResponse(
                provider="vibevoice",
                status="error",
                message=f"VibeVoice-ASR failed to load: {main._vibevoice_load_error}",
            )
        if main._vibevoice_load_thread is not None and main._vibevoice_load_thread.is_alive():
            return AsrStatusResponse(
                provider="vibevoice",
                status="loading",
                message="VibeVoice-ASR is loading the local model weights.",
            )

    return AsrStatusResponse(
        provider="vibevoice",
        status="idle",
        message="VibeVoice-ASR is not loaded. It starts only when a VibeVoice transcription request is submitted.",
    )


@router.get("/api/ai-providers")
async def get_ai_providers():
    """List language-feedback engines for the student-facing engine picker.

    Each entry reports whether it is usable right now (cloud engines need an
    API key). ``default`` is the env-configured engine used when the student
    doesn't pick one.
    """
    return {"providers": available_providers(), "default": default_provider()}


@router.post("/api/analyze", response_model=AnalysisResponse)
async def analyze_speech(
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
    # Pre-pilot research-logging identity -- all optional, all additive; a
    # caller sending none of these (every caller today) behaves exactly as
    # before. See `benchmarking/results/pilot_readiness.md`.
    participant_id: str = Form(""),
    item_id: str = Form(""),
    session_id: str = Form(""),
    attempt_id: str = Form(""),
    attempt_number: int = Form(1),
    attempt_type: str = Form("WHOLE_SENTENCE_INITIAL"),
    study_phase: str = Form(""),
    req: Request = None,
):
    """
    Analyze Chinese speech for tone, pitch, formants, speech rate, and fluency.
    If transcription is empty and asr_model is provided, transcribe first, then
    run Praat against the same audio. scene_prompt and scene_vocabulary are used
    to make AI and local feedback context-aware. scene_phrases and
    scene_suggested_answer give the AI a reference for judging whether the
    student's sentence actually means the right thing, before pronunciation
    feedback matters. scene_attempt_number drives indirect corrective feedback —
    hints only for the first two attempts on a scene, then the correct answer
    is revealed.

    verify_word is for word-practice callers that force `transcription` to a
    known target word (so tone scoring isn't at the mercy of ASR mangling a
    single syllable) — it triggers a *separate* real ASR pass on the same
    audio purely to confirm the student actually said that word, since
    otherwise nothing checks the recording's content at all.

    pinyin_hint is that same target word's own tone-marked pinyin (whatever
    is actually displayed to the student/teacher, space-separated per
    syllable, e.g. "jiě jie") — used to derive expected tones directly
    instead of a second, independent pypinyin lookup that could silently
    disagree with it (e.g. a teacher's manually corrected vocabulary pinyin,
    or a polyphonic character pypinyin reads differently out of context).

    scene_reference_curves is an optional JSON object {word: [100 floats]}
    of cached model-voice pitch-shape curves for this scene's vocabulary
    (see reference_voice.generate_scene_reference) — a word matching one of
    these keys is scored/charted against that real recording instead of the
    synthetic idealized tone-shape pattern. A missing/malformed value is
    treated as "no reference available" rather than failing the request.
    """
    if not file:
        raise HTTPException(status_code=400, detail="No audio file provided")

    if req is not None:
        client_ip = req.client.host if req.client else "unknown"
        main._check_rate_limit(f"analyze:{client_ip}", max_requests=30, window_seconds=60)

    content = await file.read()
    if len(content) > main._MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Audio file too large. Maximum size is {main._MAX_AUDIO_BYTES // (1024 * 1024)} MB.",
        )

    reference_word_curves = None
    if scene_reference_curves.strip():
        try:
            parsed = json.loads(scene_reference_curves)
            if isinstance(parsed, dict):
                reference_word_curves = {
                    str(word): curve
                    for word, curve in parsed.items()
                    if isinstance(curve, list) and curve
                }
        except (json.JSONDecodeError, TypeError):
            reference_word_curves = None

    async def _run_analysis():
        # Bounds how many of these run their CPU-bound stages at once - see
        # main.analyze_semaphore. Acquired inside the timeout so a long
        # queue wait counts against ANALYZE_TIMEOUT_SECONDS same as
        # processing time, instead of being able to wait forever.
        async with main.acquire_analysis_slot():
            return await main._do_analyze(
                content, transcription, asr_model, scene_prompt, scene_vocabulary, ai_provider, scene_image_url,
                scene_phrases, scene_suggested_answer, scene_attempt_number, verify_word, pinyin_hint,
                reference_word_curves, scene_target_text,
                participant_id=participant_id, item_id=item_id, session_id=session_id,
                attempt_id=attempt_id, attempt_number=attempt_number, attempt_type=attempt_type,
                study_phase=study_phase,
            )

    try:
        return await asyncio.wait_for(_run_analysis(), timeout=main.ANALYZE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"Analysis timed out after {main.ANALYZE_TIMEOUT_SECONDS}s. Try a shorter recording.",
        )
    except HTTPException:
        raise
    except Exception as exc:
        main.logger.exception("Error in analyze_speech")
        raise HTTPException(status_code=500, detail=f"Error analyzing speech: {exc}") from exc


@router.post("/api/analyze/stream")
async def analyze_speech_stream(
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
    req: Request = None,
):
    """Debug-only twin of /api/analyze that streams each pipeline stage as it
    completes, instead of waiting for the whole analysis to finish.

    Used exclusively by the teacher Practice Debugger so it can show live
    step-by-step progress with per-stage input/output. Students' real
    practice flow keeps calling /api/analyze unchanged — this endpoint
    reuses the same `_do_analyze` logic, it just also emits an event the
    instant each stage's `add_trace_stage` call fires.

    Response is newline-delimited SSE-style `data: {...}\\n\\n` lines:
    - {"type": "stage", ...ProcessingTraceStage fields} as each stage completes
    - {"type": "result", "result": <AnalysisResponse>} once, at the end
    - {"type": "error", "detail": "..."} instead of "result" on failure
    """
    if not file:
        raise HTTPException(status_code=400, detail="No audio file provided")

    if req is not None:
        client_ip = req.client.host if req.client else "unknown"
        main._check_rate_limit(f"analyze:{client_ip}", max_requests=30, window_seconds=60)

    content = await file.read()
    if len(content) > main._MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Audio file too large. Maximum size is {main._MAX_AUDIO_BYTES // (1024 * 1024)} MB.",
        )

    reference_word_curves = None
    if scene_reference_curves.strip():
        try:
            parsed = json.loads(scene_reference_curves)
            if isinstance(parsed, dict):
                reference_word_curves = {
                    str(word): curve
                    for word, curve in parsed.items()
                    if isinstance(curve, list) and curve
                }
        except (json.JSONDecodeError, TypeError):
            reference_word_curves = None

    async def event_generator():
        queue: "asyncio.Queue[dict]" = asyncio.Queue()
        loop_started_at = asyncio.get_event_loop().time()

        def on_stage(entry: dict) -> None:
            queue.put_nowait(entry)

        async def _run_analysis():
            # Same concurrency cap as /api/analyze - see main.analyze_semaphore.
            async with main.acquire_analysis_slot():
                return await main._do_analyze(
                    content, transcription, asr_model, scene_prompt, scene_vocabulary, ai_provider, scene_image_url,
                    scene_phrases, scene_suggested_answer, scene_attempt_number, verify_word, pinyin_hint,
                    reference_word_curves, scene_target_text, on_stage=on_stage,
                )

        task = asyncio.create_task(_run_analysis())

        try:
            while not task.done():
                if asyncio.get_event_loop().time() - loop_started_at > main.ANALYZE_TIMEOUT_SECONDS:
                    task.cancel()
                    yield _sse_line({"type": "error", "detail": f"Analysis timed out after {main.ANALYZE_TIMEOUT_SECONDS}s. Try a shorter recording."})
                    return
                try:
                    entry = await asyncio.wait_for(queue.get(), timeout=0.1)
                    yield _sse_line({"type": "stage", **entry})
                except asyncio.TimeoutError:
                    continue

            while not queue.empty():
                entry = queue.get_nowait()
                yield _sse_line({"type": "stage", **entry})

            result = task.result()
            yield _sse_line({"type": "result", "result": json.loads(result.model_dump_json())})
        except Exception as exc:
            main.logger.exception("Error in analyze_speech_stream")
            yield _sse_line({"type": "error", "detail": str(exc)})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/api/transcribe", response_model=TranscriptionResponse)
async def transcribe_speech(
    file: UploadFile = File(...),
    model: str = Form("ctwhisper"),
    vocab_hint: str = Form(""),
):
    """
    Transcribe audio to text using the requested backend ASR model.
    The default upload flow uses local Chinese/Taiwanese Whisper.
    """
    if not file:
        raise HTTPException(status_code=400, detail="No audio file provided")

    try:
        content = await file.read()
        async def run_bounded_transcription():
            async with main.acquire_analysis_slot():
                return await main.transcribe_audio_content(content, model, vocab_hint=vocab_hint)

        result = await asyncio.wait_for(
            run_bounded_transcription(), timeout=main.ANALYZE_TIMEOUT_SECONDS
        )
        if vocab_hint.strip():
            result.text = main.correct_homophones(result.text, vocab_hint)
        return result

    except HTTPException:
        raise
    except Exception as e:
        main.logger.exception("Error in transcribe_speech")
        raise HTTPException(
            status_code=500,
            detail=f"Error transcribing speech: {str(e)}"
        )
