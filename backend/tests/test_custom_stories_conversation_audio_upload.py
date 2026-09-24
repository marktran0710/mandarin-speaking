"""Covers persist_story_conversation_audio (Dual Speaking Modes plan, Epic
3): a teacher uploading a conversation turn's audio must persist the
data: URL to its own file, replacing/clearing must not orphan the old
one, and a system turn's audioUrl (character line) and a student turn's
targetAudioUrl (optional model response) must never collide."""
import base64
import io

import numpy as np
import pytest
import soundfile as sf


def _wav_data_url(duration=0.4, sample_rate=16000) -> str:
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    pcm = (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    buffer = io.BytesIO()
    sf.write(buffer, pcm, sample_rate, format="WAV", subtype="PCM_16")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:audio/wav;base64,{encoded}"


@pytest.fixture()
def isolated_uploads(tmp_path, monkeypatch):
    import services.media as media_service

    upload_dir = tmp_path / "uploads"
    (upload_dir / "audio").mkdir(parents=True)
    monkeypatch.setattr(media_service, "UPLOAD_DIR", str(upload_dir))
    monkeypatch.setattr(media_service, "AUDIO_UPLOAD_DIR", str(upload_dir / "audio"))
    return upload_dir


def _make_story(story_id: str, *, system_audio: str, student_model_audio: str = "") -> dict:
    turn = {
        "id": "system-1",
        "speaker": "system",
        "text": "你好",
        "audioUrl": system_audio,
    }
    student_turn = {
        "id": "student-1",
        "speaker": "student",
        "text": "你好！",
        "targetText": "你好！",
    }
    if student_model_audio:
        student_turn["targetAudioUrl"] = student_model_audio
    return {
        "id": story_id,
        "title": "Conversation Audio Upload Test",
        "frames": [{"imageUrl": "", "prompt": "Say hello.", "vocabulary": ""}],
        "conversationTurns": [turn, student_turn],
    }


def test_uploaded_conversation_audio_persists_to_its_own_file(admin_client, isolated_uploads):
    story_id = "test-conv-audio-upload-basic"
    try:
        response = admin_client.post(
            "/api/custom-stories", json=_make_story(story_id, system_audio=_wav_data_url()),
        )
        assert response.status_code == 200
        turns = response.json()["conversationTurns"]
        system_turn, student_turn = turns
        assert system_turn["audioUrl"].startswith("/uploads/audio/")
        assert (isolated_uploads / system_turn["audioUrl"].removeprefix("/uploads/")).exists()
        assert "targetAudioUrl" not in student_turn or not student_turn["targetAudioUrl"]
    finally:
        admin_client.delete(f"/api/custom-stories/{story_id}")


def test_system_audio_and_student_model_audio_persist_independently(admin_client, isolated_uploads):
    story_id = "test-conv-audio-both-fields"
    try:
        response = admin_client.post(
            "/api/custom-stories",
            json=_make_story(story_id, system_audio=_wav_data_url(), student_model_audio=_wav_data_url()),
        )
        assert response.status_code == 200
        system_turn, student_turn = response.json()["conversationTurns"]
        assert system_turn["audioUrl"].startswith("/uploads/audio/")
        assert student_turn["targetAudioUrl"].startswith("/uploads/audio/")
        assert system_turn["audioUrl"] != student_turn["targetAudioUrl"]
    finally:
        admin_client.delete(f"/api/custom-stories/{story_id}")


def test_reuploading_turn_audio_replaces_the_file_not_orphans_it(admin_client, isolated_uploads):
    story_id = "test-conv-audio-reupload"
    try:
        first = admin_client.post(
            "/api/custom-stories", json=_make_story(story_id, system_audio=_wav_data_url()),
        ).json()["conversationTurns"][0]
        old_path = isolated_uploads / first["audioUrl"].removeprefix("/uploads/")
        assert old_path.exists()

        second = admin_client.post(
            "/api/custom-stories", json=_make_story(story_id, system_audio=_wav_data_url()),
        ).json()["conversationTurns"][0]

        assert second["audioUrl"] != first["audioUrl"]
        assert not old_path.exists()
    finally:
        admin_client.delete(f"/api/custom-stories/{story_id}")


def test_clearing_turn_audio_removes_the_file(admin_client, isolated_uploads):
    story_id = "test-conv-audio-clear"
    try:
        first = admin_client.post(
            "/api/custom-stories", json=_make_story(story_id, system_audio=_wav_data_url()),
        ).json()["conversationTurns"][0]
        old_path = isolated_uploads / first["audioUrl"].removeprefix("/uploads/")
        assert old_path.exists()

        cleared = admin_client.post(
            "/api/custom-stories", json=_make_story(story_id, system_audio=""),
        ).json()["conversationTurns"][0]

        assert cleared["audioUrl"] == ""
        assert not old_path.exists()
    finally:
        admin_client.delete(f"/api/custom-stories/{story_id}")


def test_deleting_the_story_cleans_up_conversation_audio_files(admin_client, isolated_uploads):
    story_id = "test-conv-audio-delete-cleanup"
    saved = admin_client.post(
        "/api/custom-stories",
        json=_make_story(story_id, system_audio=_wav_data_url(), student_model_audio=_wav_data_url()),
    ).json()
    system_turn, student_turn = saved["conversationTurns"]
    system_path = isolated_uploads / system_turn["audioUrl"].removeprefix("/uploads/")
    model_path = isolated_uploads / student_turn["targetAudioUrl"].removeprefix("/uploads/")
    assert system_path.exists()
    assert model_path.exists()

    assert admin_client.delete(f"/api/custom-stories/{story_id}").status_code == 200

    assert not system_path.exists()
    assert not model_path.exists()
