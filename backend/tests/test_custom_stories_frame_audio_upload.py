"""Covers persist_story_frame_audio: a teacher uploading or recording a
scene's real model audio (not the /generate-model-voice TTS endpoint) must
(a) save the data: URL to its own file and (b) automatically derive
vocabularyReferenceCurves from that real recording, so the "target shape" a
student practices against reflects the actual final model audio instead of
staying stuck on whatever was there before (or nothing at all)."""
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
    import services.media as media_service

    upload_dir = tmp_path / "uploads"
    (upload_dir / "audio").mkdir(parents=True)
    (upload_dir / "story_audio").mkdir(parents=True)
    monkeypatch.setattr(media_service, "UPLOAD_DIR", str(upload_dir))
    monkeypatch.setattr(media_service, "AUDIO_UPLOAD_DIR", str(upload_dir / "audio"))
    monkeypatch.setattr(media_service, "STORY_AUDIO_UPLOAD_DIR", str(upload_dir / "story_audio"))
    return upload_dir


def _make_story(story_id: str, audio_url: str) -> dict:
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
        "listenAudioUrl": audio_url,
        "listenAudioSource": "teacher",
    }
    return {
        "id": story_id,
        "title": "Frame Audio Upload Test",
        "frames": [frame],
    }


def test_uploaded_audio_persists_and_derives_reference_curves(admin_client, isolated_uploads):
    story_id = "test-frame-audio-upload-basic"
    try:
        response = admin_client.post(
            "/api/custom-stories", json=_make_story(story_id, _wav_data_url())
        )
        assert response.status_code == 200
        frame = response.json()["frames"][0]

        assert frame["listenAudioUrl"].startswith("/uploads/audio/")
        assert frame["listenAudioSource"] == "teacher"
        relative = frame["listenAudioUrl"].removeprefix("/uploads/")
        assert (isolated_uploads / relative).exists()

        # No call to /generate-model-voice was made — the curves must come
        # from persist_story_frame_audio's own extraction, straight off the
        # uploaded recording.
        curves = json.loads(frame["vocabularyReferenceCurves"])
        sentence_curves = json.loads(frame["sentenceReferenceCurves"])
        assert sentence_curves
        audio_urls = json.loads(frame["vocabularyAudioUrls"])
        assert len(curves) == 2  # 咖啡, 喝 — both appear in the sentence
        assert len(audio_urls) == 2
        for curve, url in zip(curves, audio_urls):
            assert len(curve) == 100
            assert url.startswith("/uploads/story_audio/")
            assert (isolated_uploads / url.removeprefix("/uploads/")).exists()
    finally:
        admin_client.delete(f"/api/custom-stories/{story_id}")


def test_reuploading_audio_replaces_files_and_curves(admin_client, isolated_uploads):
    story_id = "test-frame-audio-reupload"
    try:
        first = admin_client.post(
            "/api/custom-stories", json=_make_story(story_id, _wav_data_url())
        ).json()["frames"][0]
        old_audio_path = isolated_uploads / first["listenAudioUrl"].removeprefix("/uploads/")
        old_word_urls = json.loads(first["vocabularyAudioUrls"])

        second = admin_client.post(
            "/api/custom-stories",
            json={
                **_make_story(story_id, _wav_data_url()),
                "frames": [{**_make_story(story_id, _wav_data_url())["frames"][0]}],
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
        admin_client.delete(f"/api/custom-stories/{story_id}")


def test_clearing_audio_removes_the_file_and_resets_curves(admin_client, isolated_uploads):
    """A teacher clicking "Remove" on model audio (not replacing it with a
    new recording) must not leave an orphaned file or stale reference
    curves behind — otherwise the UI shows "no model audio" while scoring
    keeps silently comparing students against a recording that no longer
    exists anywhere in the story."""
    story_id = "test-frame-audio-clear"
    try:
        first = admin_client.post(
            "/api/custom-stories", json=_make_story(story_id, _wav_data_url())
        ).json()["frames"][0]
        old_audio_path = isolated_uploads / first["listenAudioUrl"].removeprefix("/uploads/")
        old_word_urls = json.loads(first["vocabularyAudioUrls"])
        assert old_audio_path.exists()
        assert old_word_urls

        cleared_story = _make_story(story_id, "")
        cleared = admin_client.post("/api/custom-stories", json=cleared_story).json()["frames"][0]

        assert cleared["listenAudioUrl"] == ""
        assert not old_audio_path.exists()
        for old_word_url in old_word_urls:
            if old_word_url:
                assert not (isolated_uploads / old_word_url.removeprefix("/uploads/")).exists()
        assert json.loads(cleared["vocabularyAudioUrls"]) == []
        assert json.loads(cleared["vocabularyReferenceCurves"]) == []
        assert json.loads(cleared["sentenceReferenceCurves"]) == {}
    finally:
        admin_client.delete(f"/api/custom-stories/{story_id}")


def test_no_curves_without_sentence_text(admin_client, isolated_uploads):
    """A frame with model audio but no suggested-answer/listen-script text
    has nothing to align words against — extraction is skipped rather than
    raising, so the story save still succeeds."""
    story_id = "test-frame-audio-no-text"
    try:
        story = _make_story(story_id, _wav_data_url())
        story["frames"][0]["suggestedAnswer"] = ""
        story["frames"][0]["listenScript"] = ""

        response = admin_client.post("/api/custom-stories", json=story)
        assert response.status_code == 200
        frame = response.json()["frames"][0]
        assert frame["listenAudioUrl"].startswith("/uploads/audio/")
        assert not frame.get("vocabularyReferenceCurves")
    finally:
        admin_client.delete(f"/api/custom-stories/{story_id}")
