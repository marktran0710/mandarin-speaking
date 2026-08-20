"""Caps concurrent CPU-bound work (Praat, local ASR) behind /api/analyze -
without this, a classroom of ~50 students recording around the same moment
would spin up dozens of simultaneous analyses and thrash every core. See
main.analyze_semaphore and its usage in routers/asr.py.
"""
import asyncio
import io

import pytest
from fastapi import UploadFile

import main
from routers import asr


class _FakeAnalysisResult:
    def model_dump_json(self) -> str:
        return "{}"


def _text_form_args() -> dict:
    """Explicit string/int values for every Form(...) param analyze_speech
    and analyze_speech_stream take. Calling the route function directly
    (not through the ASGI layer) skips FastAPI's Form-default resolution,
    so the `Form(...)` sentinel objects themselves would otherwise leak
    through as the "default" values."""
    return dict(
        transcription="", asr_model="", scene_prompt="", scene_vocabulary="",
        ai_provider="", scene_image_url="", scene_phrases="",
        scene_suggested_answer="", scene_target_text="",
        scene_attempt_number=1, verify_word="", pinyin_hint="",
        scene_reference_curves="",
    )


@pytest.mark.asyncio
async def test_analyze_speech_caps_concurrent_cpu_bound_work(monkeypatch):
    limit = 2
    monkeypatch.setattr(main, "analyze_semaphore", asyncio.Semaphore(limit))

    in_flight = 0
    peak = 0

    async def fake_do_analyze(*args, **kwargs):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.05)
        in_flight -= 1
        return {"ok": True}

    monkeypatch.setattr(main, "_do_analyze", fake_do_analyze)

    async def make_request():
        upload = UploadFile(file=io.BytesIO(b"fake wav bytes"), filename="test.wav")
        return await asr.analyze_speech(
            file=upload,
            **_text_form_args(),
            participant_id="", item_id="", session_id="", attempt_id="",
            attempt_number=1, attempt_type="WHOLE_SENTENCE_INITIAL", study_phase="",
        )

    await asyncio.gather(*(make_request() for _ in range(limit * 3)))

    assert peak == limit


@pytest.mark.asyncio
async def test_analyze_speech_stream_shares_the_same_concurrency_cap(monkeypatch):
    limit = 2
    monkeypatch.setattr(main, "analyze_semaphore", asyncio.Semaphore(limit))

    in_flight = 0
    peak = 0

    async def fake_do_analyze(*args, **kwargs):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.05)
        in_flight -= 1
        return _FakeAnalysisResult()

    monkeypatch.setattr(main, "_do_analyze", fake_do_analyze)

    async def drain_stream():
        upload = UploadFile(file=io.BytesIO(b"fake wav bytes"), filename="test.wav")
        response = await asr.analyze_speech_stream(file=upload, **_text_form_args())
        async for _ in response.body_iterator:
            pass

    await asyncio.gather(*(drain_stream() for _ in range(limit * 3)))

    assert peak == limit
