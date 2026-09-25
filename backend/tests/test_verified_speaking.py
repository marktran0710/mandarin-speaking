"""Focused contract tests for server-owned speaking analysis."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import routers.verified_speaking as verified_speaking


class FakeUpload:
    def __init__(self, content: bytes):
        self.content = content

    async def read(self):
        return self.content

    async def seek(self, offset: int):
        assert offset == 0


class FakeCursor:
    def __init__(self, *, one=None, many=None):
        self.one = one
        self.many = many if many is not None else []

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.many


class FakeDb:
    def __init__(self, *, story, attempts=None):
        self.story = story
        self.attempts = attempts or []
        self.queries = []

    def execute(self, query, params=()):
        self.queries.append((query, params))
        if "FROM audio_records" in query:
            return FakeCursor(many=self.attempts)
        if "FROM custom_stories" in query:
            return FakeCursor(one=self.story)
        raise AssertionError(f"Unexpected query: {query}")


class Slot:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _main_stub(payload=None, error=None):
    calls = []

    class Analysis:
        def model_dump(self):
            return payload or {
                "transcription": "server transcript",
                "content_match": True,
                "pronunciation_mastery": {"passed": True},
            }

    class Main:
        _MAX_AUDIO_BYTES = 10_000
        ANALYZE_TIMEOUT_SECONDS = 5
        logger = SimpleNamespace(exception=lambda *args: None)

        def acquire_analysis_slot(self):
            return Slot()

        async def _do_analyze(self, *args, **kwargs):
            calls.append((args, kwargs))
            if error:
                raise error
            return Analysis()

        async def save_uploaded_audio(self, file, record_id, owner_id):
            return f"/uploads/audio/{record_id}.wav"

        def remove_uploaded_file(self, url):
            calls.append(("remove", url))

    return Main(), calls


def _patch_db(monkeypatch, db):
    @contextmanager
    def connect_db():
        yield db

    monkeypatch.setattr(verified_speaking, "connect_db", connect_db)


@pytest.mark.asyncio
async def test_verified_analysis_uses_published_scene_context(monkeypatch):
    story = {
        "id": "story-1",
        "frames": [{
            "imageUrl": "/scene.png",
            "prompt": "Server prompt",
            "vocabulary": "房間,桌子",
            "suggestedAnswer": "這是房間。",
            "listenScript": "這是房間。",
        }],
    }
    db = FakeDb(story=story)
    _patch_db(monkeypatch, db)
    main_stub, calls = _main_stub()
    monkeypatch.setattr(verified_speaking, "_main_module", lambda: main_stub)
    persisted = {}

    def save_verified(**kwargs):
        persisted.update(kwargs)
        return {"id": "record-1"}

    main_stub.save_verified_audio_record = save_verified

    result = await verified_speaking.analyze_verified_speech(
        file=FakeUpload(b"audio-one"),
        attempt_id="attempt-1",
        story_id="story-1",
        base_story_id="",
        scene_index=0,
        difficulty_level="easy",
        asr_model="groq",
        ai_provider="groq",
        transcription="client transcript hint",
        conversation_id="",
        turn_id="",
        turn_index=None,
        identity=SimpleNamespace(id="student-1"),
    )

    assert result["serverVerified"] is True
    assert result["audioRecordId"] == "record-1"
    assert result["progressionEligible"] is True
    assert result["verdicts"] == {
        "pronunciationPassed": True,
        "contentPassed": True,
        "masteryPassed": True,
    }
    assert persisted["topic_id"] == "story-1"
    assert persisted["scene_index"] == 0
    assert persisted["student_id"] == "student-1"
    analysis_args, _ = calls[0]
    assert analysis_args[3:9] == (
        "Server prompt",
        "房間,桌子",
        "groq",
        "/scene.png",
        "",
        "這是房間。",
    )
    assert calls[0][1]["scene_attempt_number"] == 1
    assert calls[0][1]["verify_word"] == ""
    assert calls[0][1]["pinyin_hint"] == ""
    assert calls[0][1]["reference_word_curves"] == {}
    assert calls[0][1]["scene_target_text"] == story["frames"][0]["listenScript"]
    assert calls[0][1]["attempt_id"] == "attempt-1"
    assert all("client" not in str(query) for query, _ in db.queries)


@pytest.mark.asyncio
async def test_same_verified_attempt_is_idempotent_without_reanalysis(monkeypatch):
    content = b"audio-one"
    import hashlib

    story = {"id": "story-1", "frames": [{"prompt": "p"}]}
    existing = {
        "id": "record-1",
        "student_id": "student-1",
        "audio_sha256": hashlib.sha256(content).hexdigest(),
        "server_verified_at": "2026-09-18T00:00:00+00:00",
        "praat_metrics": {"content_match": True},
        "topic_id": "story-1",
        "image_index": 0,
    }
    db = FakeDb(story=story, attempts=[existing])
    _patch_db(monkeypatch, db)
    main_stub, calls = _main_stub()
    monkeypatch.setattr(verified_speaking, "_main_module", lambda: main_stub)
    main_stub.save_verified_audio_record = lambda **kwargs: pytest.fail("must not persist twice")

    result = await verified_speaking.analyze_verified_speech(
        file=FakeUpload(content), attempt_id="attempt-1", story_id="story-1",
        base_story_id="", scene_index=0, difficulty_level="easy", asr_model="",
        ai_provider="", transcription="", conversation_id="", turn_id="", turn_index=None,
        identity=SimpleNamespace(id="student-1"),
    )

    assert result["audioRecordId"] == "record-1"
    assert calls == []


@pytest.mark.asyncio
async def test_same_attempt_with_different_audio_is_rejected(monkeypatch):
    import hashlib

    existing = {
        "id": "record-1", "student_id": "student-1",
        "audio_sha256": hashlib.sha256(b"audio-one").hexdigest(),
        "server_verified_at": "2026-09-18T00:00:00+00:00",
        "praat_metrics": {}, "topic_id": "story-1", "image_index": 0,
    }
    _patch_db(monkeypatch, FakeDb(story={"id": "story-1", "frames": [{}]}, attempts=[existing]))
    main_stub, calls = _main_stub()
    monkeypatch.setattr(verified_speaking, "_main_module", lambda: main_stub)

    with pytest.raises(HTTPException) as exc:
        await verified_speaking.analyze_verified_speech(
            file=FakeUpload(b"audio-two"), attempt_id="attempt-1", story_id="story-1",
            base_story_id="", scene_index=0, difficulty_level="easy", asr_model="",
            ai_provider="", transcription="", identity=SimpleNamespace(id="student-1"),
        )
    assert exc.value.status_code == 409
    assert calls == []


@pytest.mark.asyncio
async def test_unverified_legacy_attempt_cannot_be_upgraded(monkeypatch):
    existing = {
        "id": "legacy-1", "student_id": "student-1", "audio_sha256": None,
        "server_verified_at": None, "praat_metrics": {"client": True},
        "topic_id": "story-1", "image_index": 0,
    }
    _patch_db(monkeypatch, FakeDb(story={"id": "story-1", "frames": [{}]}, attempts=[existing]))
    main_stub, calls = _main_stub()
    monkeypatch.setattr(verified_speaking, "_main_module", lambda: main_stub)

    with pytest.raises(HTTPException) as exc:
        await verified_speaking.analyze_verified_speech(
            file=FakeUpload(b"audio-one"), attempt_id="attempt-1", story_id="story-1",
            base_story_id="", scene_index=0, difficulty_level="easy", asr_model="",
            ai_provider="", transcription="", identity=SimpleNamespace(id="student-1"),
        )
    assert exc.value.status_code == 409
    assert calls == []


@pytest.mark.asyncio
async def test_failed_analysis_never_persists_verified_audio(monkeypatch):
    _patch_db(monkeypatch, FakeDb(story={"id": "story-1", "frames": [{"prompt": "p"}]}))
    main_stub, calls = _main_stub(error=RuntimeError("analyzer failed"))
    monkeypatch.setattr(verified_speaking, "_main_module", lambda: main_stub)
    main_stub.save_verified_audio_record = lambda **kwargs: pytest.fail("must not persist failed analysis")

    with pytest.raises(HTTPException) as exc:
        await verified_speaking.analyze_verified_speech(
            file=FakeUpload(b"audio-one"), attempt_id="attempt-1", story_id="story-1",
            base_story_id="", scene_index=0, difficulty_level="easy", asr_model="",
            ai_provider="", transcription="", conversation_id="", turn_id="", turn_index=None,
            identity=SimpleNamespace(id="student-1"),
        )
    assert exc.value.status_code == 500
    assert not any(call[0] == "remove" for call in calls if isinstance(call, tuple))
