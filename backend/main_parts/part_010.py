

def _transcribe_with_vibevoice_sync(audio_content: bytes) -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
        tmp_file.write(audio_content)
        tmp_path = tmp_file.name

    try:
        import torch

        processor, model, device = _get_vibevoice_asr_model()
        inputs = processor(
            audio=tmp_path,
            sampling_rate=None,
            return_tensors="pt",
            add_generation_prompt=True,
        )
        inputs = {
            key: value.to(device) if isinstance(value, torch.Tensor) else value
            for key, value in inputs.items()
        }

        with torch.no_grad():
            output_ids = model.generate(
                **inputs,
                max_new_tokens=VIBEVOICE_MAX_NEW_TOKENS,
                max_time=VIBEVOICE_MAX_TIME_SECONDS,
                do_sample=False,
                num_beams=1,
                pad_token_id=processor.pad_id,
                eos_token_id=processor.tokenizer.eos_token_id,
            )

        generated_ids = output_ids[0, inputs["input_ids"].shape[1]:]
        generated_text = processor.decode(generated_ids, skip_special_tokens=True)
        try:
            segments = processor.post_process_transcription(generated_text)
        except Exception:
            segments = []
        result = {"raw_text": generated_text, "segments": segments}
        text = _extract_vibevoice_text(result)
        if not text:
            raise RuntimeError("VibeVoice-ASR did not return transcription text.")
        return text
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


async def transcribe_with_vibevoice(audio_content: bytes) -> TranscriptionResponse:
    """Transcribe using local VibeVoice-ASR through Transformers on the backend."""
    try:
        text = await asyncio.wait_for(
            run_in_threadpool(_transcribe_with_vibevoice_sync, audio_content),
            timeout=VIBEVOICE_MAX_TIME_SECONDS + 20,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=(
                "VibeVoice-ASR transcription is too slow on this machine. "
                "Try a shorter recording or run the backend on a GPU."
            ),
        ) from exc
    return TranscriptionResponse(text=text, model="vibevoice")


# ── Routers (imported here, after all shared models/helpers above are
# defined, since each router imports names back from this module) ─────────
from routers.admin import router as admin_router  # noqa: E402
from routers.knowledge_analytics import router as knowledge_analytics_router  # noqa: E402
from routers.asr import router as asr_router  # noqa: E402
from routers.analysis_v2 import router as analysis_v2_router  # noqa: E402
from routers.audio import router as audio_router  # noqa: E402
from routers.help_requests import router as help_requests_router  # noqa: E402
from routers.media import router as media_router  # noqa: E402
from routers.measurement import router as measurement_router  # noqa: E402
from routers.pilot import router as pilot_router  # noqa: E402
from routers.pinyin import router as pinyin_router  # noqa: E402
from routers.quiz_review import router as quiz_review_router  # noqa: E402
from routers.speaking_progress import router as speaking_progress_router  # noqa: E402
from routers.stories import router as stories_router  # noqa: E402
from routers.students import router as students_router  # noqa: E402
from routers.teachers import router as teachers_router  # noqa: E402
from routers.submissions import router as submissions_router  # noqa: E402
from routers.teacher_review import router as teacher_review_router  # noqa: E402
from routers.tones import router as tones_router  # noqa: E402
from routers.tts import router as tts_router  # noqa: E402
from routers.vocab_quiz import router as vocab_quiz_router  # noqa: E402
app.include_router(admin_router)
app.include_router(knowledge_analytics_router)
app.include_router(asr_router)
app.include_router(analysis_v2_router)
app.include_router(audio_router)
app.include_router(help_requests_router)
app.include_router(media_router)
app.include_router(measurement_router)
app.include_router(pilot_router)
app.include_router(pinyin_router)
app.include_router(quiz_review_router)
app.include_router(speaking_progress_router)
app.include_router(stories_router)
app.include_router(students_router)
app.include_router(teachers_router)
app.include_router(submissions_router)
app.include_router(teacher_review_router)
app.include_router(tts_router)
app.include_router(tones_router)
app.include_router(vocab_quiz_router)

@app.get("/{frontend_path:path}")
def serve_frontend(frontend_path: str):
    """
    Serve the built React app from the backend port for local single-port use.
    """
    requested_file = (FRONTEND_DIST / frontend_path).resolve()

    if FRONTEND_DIST.exists() and requested_file.is_file():
        return FileResponse(requested_file)

    index_file = FRONTEND_DIST / "index.html"
    if index_file.exists():
        return FileResponse(index_file)

    raise HTTPException(
        status_code=404,
        detail="Frontend build not found. Run `npm run build` first.",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
