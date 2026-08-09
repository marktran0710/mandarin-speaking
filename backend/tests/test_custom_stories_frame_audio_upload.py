"""Covers persist_story_frame_audio: a teacher uploading or recording a
scene's real model audio (not the /generate-model-voice TTS endpoint) must
(a) save every tier's data: URL to its own file, mirroring the Medium/Hard
image-tier fix in test_custom_stories_level_tiers.py, and (b) automatically
derive vocabularyReferenceCurves from that real recording, so the "target
shape" a student practices against reflects the actual final model audio
instead of staying stuck on whatever was there before (or nothing at all)."""
import base64
import io
import json

import numpy as np
import pytest
import soundfile as sf


def _wav_data_url(duration=1.4, sample_rate=24000) -> str:
    """A short synthetic rising tone, real enough for Praat's pitch tracker
    to lock onto — same approach test_reference_voice.py uses."""
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    freq = 150 + 70 * (t / duration)
    phase = 2 * np.pi * np.cumsum(freq) / sample_rate
    pcm = (0.3 * np.sin(phase)).astype(np.float32)

    buffer = io.BytesIO()
    sf.write(buffer, pcm, sample_rate, format="WAV", subtype="PCM_16")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:audio/wav;base64,{encoded}"


@pytest.fixture()
def isolated_uploads(tmp_path, monkeypatch):
    """Points every upload dir at a temp dir so this test's saved files
    don't land in (or get cleaned from) the real uploads folder."""
    import main

    upload_dir = tmp_path / "uploads"
    (upload_dir / "audio").mkdir(parents=True)
    (upload_dir / "story_audio").mkdir(parents=True)
    monkeypatch.setattr(main, "UPLOAD_DIR", str(upload_dir))
    monkeypatch.setattr(main, "AUDIO_UPLOAD_DIR", str(upload_dir / "audio"))
    monkeypatch.setattr(main, "STORY_AUDIO_UPLOAD_DIR", str(upload_dir / "story_audio"))
    return upload_dir


def _make_story(story_id: str, audio_field: str, audio_url: str) -> dict:
    frame = {
        "imageUrl": "",
        "prompt": "Describe the picture.",
        # Word order matches reading order in the sentence below — the
        # per-word slicing heuristic searches forward through the sentence
        # text as it processes each vocab word in turn (see
        # reference_voice.slice_reference_word_span), so an out-of-order
        # vocab list would make an earlier word "unfindable" after a later
        # one has already advanced the search past it.
        "vocabulary": "喝, 咖啡",
        "vocabularyTranslation": "to drink, coffee",
        "suggestedAnswer": "我想喝咖啡。",
        "listenScript": "我想喝咖啡。",
        "vocabularyMedium": "咖啡廳, 享受",
        "suggestedAnswerMedium": "我想在咖啡廳享受一杯咖啡。",
        "listenScriptMedium": "我想在咖啡廳享受一杯咖啡。",
    }
    frame[audio_field] = audio_url
    return {
        "id": story_id,
        "title": "Frame Audio Upload Test",
        "learningGoal": "Check uploaded model audio persists and scores itself",
        "frames": [frame],
        "narrativeMode": "describe",
    }


def test_uploaded_audio_persists_and_derives_reference_curves(client, isolated_uploads):
    story_id = "test-frame-audio-upload-basic"
    try:
        response = client.post(
            "/api/custom-stories", json=_make_story(story_id, "listenAudioUrl", _wav_data_url())
        )
        assert response.status_code == 200
        frame = response.json()["frames"][0]

        assert frame["listenAudioUrl"].startswith("/uploads/audio/")
        relative = frame["listenAudioUrl"].removeprefix("/uploads/")
        assert (isolated_uploads / relative).exists()

        # No call to /generate-model-voice was made — the curves must come
        # from persist_story_frame_audio's own extraction, straight off the
        # uploaded recording.
        curves = json.loads(frame["vocabularyReferenceCurves"])
        audio_urls = json.loads(frame["vocabularyAudioUrls"])
        assert len(curves) == 2  # 咖啡, 喝 — both appear in the sentence
        assert len(audio_urls) == 2
        for curve, url in zip(curves, audio_urls):
            assert len(curve) == 100
            assert url.startswith("/uploads/story_audio/")
            assert (isolated_uploads / url.removeprefix("/uploads/")).exists()
    finally:
        client.delete(f"/api/custom-stories/{story_id}")


def test_uploaded_audio_is_tier_aware(client, isolated_uploads):
    """Root cause this guards against: persist_story_frame_audio only ever
    read/wrote the base listenAudioUrl field, so uploading Medium/Hard audio
    was silently dropped (stayed a giant data: URL in the DB, never became a
    real file, never got a reference curve)."""
    story_id = "test-frame-audio-upload-tiers"
    try:
        response = client.post(
            "/api/custom-stories",
            json=_make_story(story_id, "listenAudioUrlMedium", _wav_data_url()),
        )
        assert response.status_code == 200
        frame = response.json()["frames"][0]

        assert frame["listenAudioUrlMedium"].startswith("/uploads/audio/")
        curves = json.loads(frame["vocabularyReferenceCurvesMedium"])
        assert len(curves) == 2  # 咖啡廳, 享受
        assert all(len(c) == 100 for c in curves)
    finally:
        client.delete(f"/api/custom-stories/{story_id}")


def test_reuploading_audio_replaces_files_and_curves(client, isolated_uploads):
    story_id = "test-frame-audio-reupload"
    try:
        first = client.post(
            "/api/custom-stories", json=_make_story(story_id, "listenAudioUrl", _wav_data_url())
        ).json()["frames"][0]
        old_audio_path = isolated_uploads / first["listenAudioUrl"].removeprefix("/uploads/")
        old_word_urls = json.loads(first["vocabularyAudioUrls"])

        second = client.post(
            "/api/custom-stories",
            json={
                **_make_story(story_id, "listenAudioUrl", _wav_data_url()),
                "frames": [{**_make_story(story_id, "listenAudioUrl", _wav_data_url())["frames"][0]}],
            },
        ).json()["frames"][0]

        assert second["listenAudioUrl"] != first["listenAudioUrl"]
        assert not old_audio_path.exists()  # replaced, not orphaned
        for old_word_url in old_word_urls:
            if old_word_url:
                assert not (isolated_uploads / old_word_url.removeprefix("/uploads/")).exists()

        new_curves = json.loads(second["vocabularyReferenceCurves"])
        assert len(new_curves) == 2
    finally:
        client.delete(f"/api/custom-stories/{story_id}")


def test_no_curves_without_sentence_text(client, isolated_uploads):
    """A frame with model audio but no suggested-answer/listen-script text
    has nothing to align words against — extraction is skipped rather than
    raising, so the story save still succeeds."""
    story_id = "test-frame-audio-no-text"
    try:
        story = _make_story(story_id, "listenAudioUrl", _wav_data_url())
        story["frames"][0]["suggestedAnswer"] = ""
        story["frames"][0]["listenScript"] = ""

        response = client.post("/api/custom-stories", json=story)
        assert response.status_code == 200
        frame = response.json()["frames"][0]
        assert frame["listenAudioUrl"].startswith("/uploads/audio/")
        assert not frame.get("vocabularyReferenceCurves")
    finally:
        client.delete(f"/api/custom-stories/{story_id}")
