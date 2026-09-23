"""Dual Speaking Modes plan, Epic 2: server-authoritative conversation
target resolution for /api/analyze/verified. A conversation response must
be scored against the exact resolved turn's targetText, never a
client-submitted value and never the legacy scene's suggestedAnswer/
listenScript."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import routers.verified_speaking as verified_speaking
from tests.test_verified_speaking import FakeDb, FakeUpload, _main_stub, _patch_db

CONVERSATION_STORY = {
    "id": "story-1",
    "frames": [{
        "imageUrl": "/scene.png",
        "prompt": "Legacy scene prompt",
        "vocabulary": "",
        "suggestedAnswer": "這是房間。",
        "listenScript": "這是房間。",
    }],
    "conversation_turns": [
        {"id": "system-1", "speaker": "system", "text": "你週末要做什麼？"},
        {"id": "student-1", "speaker": "student", "text": "我想去喝下午茶", "targetText": "我想跟朋友去喝下午茶。"},
    ],
}


class TestResolveVerifiedSpeakingTarget:
    def test_no_conversation_identity_uses_the_legacy_scene_target(self, monkeypatch):
        _patch_db(monkeypatch, FakeDb(story=CONVERSATION_STORY))
        scene = verified_speaking.resolve_verified_speaking_target("story-1", 0, "easy")
        assert scene["target_text"] == "這是房間。"

    def test_conversation_turn_resolves_to_its_own_target_text_not_the_scene(self, monkeypatch):
        _patch_db(monkeypatch, FakeDb(story=CONVERSATION_STORY))
        scene = verified_speaking.resolve_verified_speaking_target(
            "story-1", 0, "easy", conversation_id="conversation:story-1", turn_id="student-1", turn_index=1,
        )
        assert scene["target_text"] == "我想跟朋友去喝下午茶。"
        assert scene["reference_word_curves"] == {}

    def test_conversation_turn_falls_back_to_raw_text_with_no_target_text(self, monkeypatch):
        story = {
            **CONVERSATION_STORY,
            "conversation_turns": [
                {"id": "system-1", "speaker": "system", "text": "你好"},
                {"id": "student-1", "speaker": "student", "text": "你好！"},
            ],
        }
        _patch_db(monkeypatch, FakeDb(story=story))
        scene = verified_speaking.resolve_verified_speaking_target(
            "story-1", 0, "easy", conversation_id="c", turn_id="student-1", turn_index=1,
        )
        assert scene["target_text"] == "你好！"

    def test_turn_index_must_match_turn_id(self, monkeypatch):
        _patch_db(monkeypatch, FakeDb(story=CONVERSATION_STORY))
        with pytest.raises(HTTPException) as exc:
            verified_speaking.resolve_verified_speaking_target(
                "story-1", 0, "easy", conversation_id="c", turn_id="student-1", turn_index=0,
            )
        assert exc.value.status_code == 422

    def test_an_unknown_turn_id_is_rejected(self, monkeypatch):
        _patch_db(monkeypatch, FakeDb(story=CONVERSATION_STORY))
        with pytest.raises(HTTPException) as exc:
            verified_speaking.resolve_verified_speaking_target(
                "story-1", 0, "easy", conversation_id="c", turn_id="not-a-real-turn",
            )
        assert exc.value.status_code == 422

    def test_a_system_turn_cannot_be_analyzed_as_a_student_response(self, monkeypatch):
        _patch_db(monkeypatch, FakeDb(story=CONVERSATION_STORY))
        with pytest.raises(HTTPException) as exc:
            verified_speaking.resolve_verified_speaking_target(
                "story-1", 0, "easy", conversation_id="c", turn_id="system-1", turn_index=0,
            )
        assert exc.value.status_code == 422

    def test_a_turn_id_from_another_story_is_rejected(self, monkeypatch):
        # Only this story's own conversation_turns are ever searched - a turn
        # id that happens to exist on a different story is simply not found.
        _patch_db(monkeypatch, FakeDb(story=CONVERSATION_STORY))
        with pytest.raises(HTTPException) as exc:
            verified_speaking.resolve_verified_speaking_target(
                "story-1", 0, "easy", conversation_id="c", turn_id="turn-from-another-story",
            )
        assert exc.value.status_code == 422

    def test_a_story_with_no_conversation_turns_rejects_conversation_identity(self, monkeypatch):
        _patch_db(monkeypatch, FakeDb(story={"id": "story-1", "frames": [{"prompt": "p"}]}))
        with pytest.raises(HTTPException) as exc:
            verified_speaking.resolve_verified_speaking_target(
                "story-1", 0, "easy", conversation_id="c", turn_id="student-1",
            )
        assert exc.value.status_code == 422


class TestAnalyzeVerifiedSpeechWithConversationIdentity:
    @pytest.mark.asyncio
    async def test_scores_against_the_resolved_conversation_target_not_the_scene(self, monkeypatch):
        _patch_db(monkeypatch, FakeDb(story=CONVERSATION_STORY))
        main_stub, calls = _main_stub()
        monkeypatch.setattr(verified_speaking, "_main_module", lambda: main_stub)
        main_stub.save_verified_audio_record = lambda **kwargs: {"id": "record-1"}

        result = await verified_speaking.analyze_verified_speech(
            file=FakeUpload(b"audio-one"), attempt_id="attempt-1", story_id="story-1",
            base_story_id="", scene_index=0, difficulty_level="easy", asr_model="",
            ai_provider="", transcription="",
            conversation_id="conversation:story-1", turn_id="student-1", turn_index=1,
            identity=SimpleNamespace(id="student-1"),
        )

        assert result["serverVerified"] is True
        analysis_args, _ = calls[0]
        # _do_analyze's target_text positional argument must be the
        # conversation turn's targetText, never the scene's
        # suggestedAnswer/listenScript ("這是房間。" in this fixture).
        assert analysis_args[13] == "我想跟朋友去喝下午茶。"
        assert analysis_args[8] == "這是房間。"  # scene's own suggested_answer, untouched

    @pytest.mark.asyncio
    async def test_rejects_a_system_turn_submitted_as_the_students_own_target(self, monkeypatch):
        _patch_db(monkeypatch, FakeDb(story=CONVERSATION_STORY))
        main_stub, calls = _main_stub()
        monkeypatch.setattr(verified_speaking, "_main_module", lambda: main_stub)

        with pytest.raises(HTTPException) as exc:
            await verified_speaking.analyze_verified_speech(
                file=FakeUpload(b"audio-one"), attempt_id="attempt-1", story_id="story-1",
                base_story_id="", scene_index=0, difficulty_level="easy", asr_model="",
                ai_provider="", transcription="",
                conversation_id="conversation:story-1", turn_id="system-1", turn_index=0,
                identity=SimpleNamespace(id="student-1"),
            )
        assert exc.value.status_code == 422
        assert calls == []
