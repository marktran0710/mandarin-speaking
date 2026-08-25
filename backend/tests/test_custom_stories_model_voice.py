"""Tests for the generate-model-voice endpoints: synthesizing a scene's
model sentence and per-word reference clips, and persisting them onto the
frame. The TTS network call + MP3 decode are mocked (see
test_reference_voice.py for the un-mocked pipeline); this file focuses on
the HTTP contract, tier handling, and frame persistence.
"""
import json
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest


def _make_story(story_id):
    frame = {
        "imageUrl": "",
        "prompt": "Describe the picture.",
        "vocabulary": "咖啡, 喝",
        "vocabularyTranslation": "coffee, to drink",
        "suggestedAnswer": "我想喝咖啡。",
        "vocabularyMedium": "咖啡廳, 享受",
        "suggestedAnswerMedium": "我想在咖啡廳享受一杯咖啡。",
    }
    return {
        "id": story_id,
        "title": "Model Voice Test",
        "frames": [frame],
    }


def _synthetic_rising_tone_pcm(duration=1.4, sample_rate=24000):
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    freq = 150 + 70 * (t / duration)
    phase = 2 * np.pi * np.cumsum(freq) / sample_rate
    return (0.3 * np.sin(phase)).astype(np.float32), sample_rate


@pytest.fixture
def mocked_tts():
    pcm, sample_rate = _synthetic_rising_tone_pcm()
    with patch("reference_voice.synthesize_sentence_mp3", new_callable=AsyncMock) as synth, \
         patch("reference_voice.decode_mp3_to_pcm") as decode:
        synth.return_value = b"fake-mp3-bytes"
        decode.return_value = (pcm, sample_rate)
        yield


def test_generate_model_voice_persists_sentence_and_word_fields(client, mocked_tts):
    story_id = "test-model-voice-basic"
    try:
        client.post("/api/custom-stories", json=_make_story(story_id))

        response = client.post(
            f"/api/custom-stories/{story_id}/generate-model-voice",
            json={"frameIndex": 0, "tier": "easy"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["tier"] == "easy"
        assert body["listenAudioUrl"].startswith("/uploads/story_audio/")
        assert body["listenAudioSource"] == "tts"
        assert json.loads(body["sentenceReferenceCurves"])
        assert body["listenScript"] == "我想喝咖啡。"
        audio_urls = json.loads(body["vocabularyAudioUrls"])
        curves = json.loads(body["vocabularyReferenceCurves"])
        assert len(audio_urls) == 2  # 咖啡, 喝
        assert len(curves) == 2
        assert all(url is None or url.startswith("/uploads/story_audio/") for url in audio_urls)

        fetched = next(
            s for s in client.get("/api/custom-stories").json() if s["id"] == story_id
        )
        frame = fetched["frames"][0]
        assert frame["listenAudioUrl"] == body["listenAudioUrl"]
        assert frame["listenAudioSource"] == "tts"
        assert json.loads(frame["vocabularyAudioUrls"]) == audio_urls
        assert json.loads(frame["sentenceReferenceCurves"])
    finally:
        client.delete(f"/api/custom-stories/{story_id}")


def test_generate_model_voice_is_tier_aware(client, mocked_tts):
    story_id = "test-model-voice-tiers"
    try:
        client.post("/api/custom-stories", json=_make_story(story_id))

        easy = client.post(
            f"/api/custom-stories/{story_id}/generate-model-voice",
            json={"frameIndex": 0, "tier": "easy"},
        )
        medium = client.post(
            f"/api/custom-stories/{story_id}/generate-model-voice",
            json={"frameIndex": 0, "tier": "medium"},
        )
        assert easy.status_code == 200
        assert medium.status_code == 200

        fetched = next(
            s for s in client.get("/api/custom-stories").json() if s["id"] == story_id
        )
        frame = fetched["frames"][0]
        # Easy and Medium tiers write to different, non-conflicting fields.
        assert frame["listenScript"] == "我想喝咖啡。"
        assert frame["listenScriptMedium"] == "我想在咖啡廳享受一杯咖啡。"
        assert frame["listenAudioUrl"] != frame["listenAudioUrlMedium"]
    finally:
        client.delete(f"/api/custom-stories/{story_id}")


def test_generate_model_voice_404s_on_missing_frame(client, mocked_tts):
    story_id = "test-model-voice-missing-frame"
    try:
        client.post("/api/custom-stories", json=_make_story(story_id))
        response = client.post(
            f"/api/custom-stories/{story_id}/generate-model-voice",
            json={"frameIndex": 5, "tier": "easy"},
        )
        assert response.status_code == 404
    finally:
        client.delete(f"/api/custom-stories/{story_id}")


def test_generate_model_voice_422s_with_no_sentence_text(client, mocked_tts):
    story_id = "test-model-voice-no-text"
    try:
        story = _make_story(story_id)
        story["frames"][0]["suggestedAnswer"] = None
        story["frames"][0]["listenScript"] = None
        client.post("/api/custom-stories", json=story)

        response = client.post(
            f"/api/custom-stories/{story_id}/generate-model-voice",
            json={"frameIndex": 0, "tier": "hard"},
        )
        assert response.status_code == 422
    finally:
        client.delete(f"/api/custom-stories/{story_id}")


def test_bulk_generate_covers_every_requested_tier_and_reports_skips(client, mocked_tts):
    story_id = "test-model-voice-bulk"
    try:
        client.post("/api/custom-stories", json=_make_story(story_id))

        response = client.post(
            f"/api/custom-stories/{story_id}/generate-model-voice-bulk",
            json={"tiers": ["easy", "medium", "hard"]},
        )
        assert response.status_code == 200
        results = response.json()["results"]
        by_tier = {r["tier"]: r for r in results}
        assert by_tier["easy"]["ok"] is True
        assert by_tier["medium"]["ok"] is True
        # Hard tier has no suggestedAnswerHard/listenScriptHard authored yet.
        assert by_tier["hard"]["ok"] is False
    finally:
        client.delete(f"/api/custom-stories/{story_id}")


def test_regenerating_replaces_rather_than_appends(client, mocked_tts):
    story_id = "test-model-voice-regenerate"
    try:
        client.post("/api/custom-stories", json=_make_story(story_id))

        first = client.post(
            f"/api/custom-stories/{story_id}/generate-model-voice",
            json={"frameIndex": 0, "tier": "easy"},
        ).json()
        second = client.post(
            f"/api/custom-stories/{story_id}/generate-model-voice",
            json={"frameIndex": 0, "tier": "easy"},
        ).json()

        # A fresh generation, not an accumulating pool.
        assert len(json.loads(second["vocabularyAudioUrls"])) == 2
        assert first["listenAudioUrl"] != second["listenAudioUrl"]
    finally:
        client.delete(f"/api/custom-stories/{story_id}")
