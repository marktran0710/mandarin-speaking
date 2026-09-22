"""Regression tests for the server-owned speaking progress contract."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from main import SpeakingProgressRequest
import routers.speaking_progress as speaking_progress


class Cursor:
    def __init__(self, one=None, many=None):
        self.one = one
        self.many = many or []

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.many


class ProgressDb:
    def __init__(self, *, verified, existing=None, stats=None, current=None):
        self.verified = verified
        self.existing = existing
        self.stats = stats if stats is not None else [{"praat_metrics": verified["praat_metrics"]}]
        self.current = current
        self.insert_params = None

    def execute(self, query, params=()):
        if "pg_advisory_xact_lock" in query:
            return Cursor()
        if "FROM speaking_progress" in query:
            return Cursor(one=self.existing)
        if "SELECT id, server_verified_at FROM audio_records" in query:
            return Cursor(one=self.current)
        if "FROM audio_records" in query and "WHERE id = %s" in query:
            return Cursor(one=self.verified)
        if "SELECT praat_metrics" in query and "server_verified_at IS NOT NULL" in query:
            return Cursor(many=self.stats)
        if "INSERT INTO speaking_progress" in query:
            self.insert_params = params
            return Cursor()
        raise AssertionError(f"Unexpected query: {query}")


def _db(monkeypatch, db):
    @contextmanager
    def connect_db():
        yield db

    monkeypatch.setattr(speaking_progress, "connect_db", connect_db)


def _record(**overrides):
    record = {
        "id": "audio-1",
        "student_id": "student-1",
        "topic_id": "story-1",
        "image_index": 0,
        "transcription": "server transcript",
        "audio_url": "/uploads/audio/audio-1.wav",
        "image_url": "/scene.png",
        "server_verified_at": datetime(2026, 9, 18, tzinfo=timezone.utc),
        "server_verification_version": "verified-speaking-stable-v1",
        "praat_metrics": {
            "tone_accuracy": 62.5,
            "fluency_score": 54.0,
            "content_match": True,
            "pronunciation_mastery": {"passed": False},
            "ai_feedback": {"vocabulary_coverage": {"score": 80, "used": ["房間"], "missing": []}},
            "pause_analysis": {"pause_count": 2, "longest_pause": 0.7},
        },
    }
    record.update(overrides)
    return record


def _progress(record_id="audio-1", **overrides):
    payload = {
        "studentId": "forged-student",
        "topicId": "tier-topic",
        "sceneIndex": 0,
        "attempts": 99,
        "bestTone": 100,
        "bestFluency": 100,
        "masteryPassed": True,
        "contentPassed": True,
        "clearedWords": ["房間"],
        "latestResult": {
            "sceneIndex": 0,
            "toneAccuracy": 1000,
            "pronScore": 1000,
            "vocabScore": 1000,
            "selfEvalContent": "good",
        },
        "baseStoryId": "story-1",
        "difficultyLevel": "easy",
        "verifiedAudioRecordId": record_id,
    }
    payload.update(overrides)
    return SpeakingProgressRequest.model_validate(payload)


@pytest.mark.asyncio
async def test_verified_progress_ignores_forged_scores_and_flags(monkeypatch):
    record = _record()
    db = ProgressDb(verified=record)
    _db(monkeypatch, db)

    result = await speaking_progress.upsert_speaking_progress(
        _progress(
            conversationId="conversation:story-1",
            turnId="student-1",
            turnIndex=1,
            promptId="story-1:conversation:student-1",
        ),
        SimpleNamespace(id="student-1"),
    )

    assert result.progressionEligible is True
    assert result.attempts == 1
    assert result.bestTone == 62.5
    assert result.bestFluency == 54.0
    assert result.masteryPassed is False
    assert result.contentPassed is True
    assert result.latestResult["toneAccuracy"] == 62.5
    assert result.latestResult["pronScore"] == 62.5
    assert result.latestResult["vocabScore"] == 80.0
    assert result.latestResult["selfEvalContent"] == "good"
    assert result.latestResult["conversationId"] == "conversation:story-1"
    assert result.latestResult["turnId"] == "student-1"
    assert result.latestResult["turnIndex"] == 1
    assert db.insert_params[11] == "audio-1"


@pytest.mark.asyncio
async def test_same_verified_record_is_idempotent(monkeypatch):
    record = _record()
    existing = {
        "attempts": 4,
        "best_tone": 62.5,
        "best_fluency": 54.0,
        "mastery_passed": False,
        "content_passed": True,
        "cleared_words": ["之前"],
        "latest_result": {"snapshotId": "audio-1", "selfEvalPronunciation": "ok"},
        "verified_audio_record_id": "audio-1",
    }
    db = ProgressDb(verified=record, existing=existing)
    _db(monkeypatch, db)

    result = await speaking_progress.upsert_speaking_progress(
        _progress(latestResult={"selfEvalContent": "good"}),
        SimpleNamespace(id="student-1"),
    )

    assert result.attempts == 4
    assert result.verifiedAudioRecordId == "audio-1"
    assert result.clearedWords == ["之前", "房間"]
    assert result.latestResult["selfEvalPronunciation"] == "ok"
    assert result.latestResult["selfEvalContent"] == "good"
    assert db.insert_params[4] == 4


@pytest.mark.parametrize(
    "changes,status",
    [
        ({"student_id": "other-student"}, 403),
        ({"server_verified_at": None}, 409),
        ({"server_verification_version": "analysis-v2"}, 409),
    ],
)
@pytest.mark.asyncio
async def test_non_progression_audio_records_are_rejected(monkeypatch, changes, status):
    record = _record(**changes)
    db = ProgressDb(verified=record)
    _db(monkeypatch, db)

    with pytest.raises(HTTPException) as exc:
        await speaking_progress.upsert_speaking_progress(
            _progress(), SimpleNamespace(id="student-1")
        )
    assert exc.value.status_code == status


@pytest.mark.asyncio
async def test_verified_record_must_match_base_story(monkeypatch):
    record = _record(topic_id="different-story")
    db = ProgressDb(verified=record)
    _db(monkeypatch, db)

    with pytest.raises(HTTPException) as exc:
        await speaking_progress.upsert_speaking_progress(
            _progress(), SimpleNamespace(id="student-1")
        )
    assert exc.value.status_code == 409
