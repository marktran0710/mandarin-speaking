import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import security.auth as auth
from routers import admin
from services.content_inventory import build_content_inventory


@pytest.fixture(autouse=True)
def clean_database():
    """These unit/isolated-route tests never access Postgres."""
    yield


def _question(word_id: str, word: str, level: str, **metadata):
    return {
        "questionId": f"{word_id}_{level.upper()}",
        "wordId": word_id,
        "targetWord": word,
        "level": level,
        "pinyin": metadata.get("pinyin", ""),
        "pos": metadata.get("pos", ""),
        "simpleEnglishMeaning": metadata.get("translation", ""),
    }


def _codes(report):
    return {finding["code"] for finding in report["findings"]}


def test_content_doctor_reports_cross_source_and_media_problems(tmp_path):
    uploads = tmp_path / "uploads"
    (uploads / "audio").mkdir(parents=True)
    (uploads / "images").mkdir()
    (uploads / "audio" / "scene.wav").write_bytes(b"scene")
    (uploads / "audio" / "word.wav").write_bytes(b"word")
    (uploads / "images" / "orphan.png").write_bytes(b"orphan")

    assessment = [
        _question("W1", "桌子", "easy", pinyin="zhuo1 zi5", pos="N", translation="table"),
        _question("W1", "桌子", "medium", pinyin="zhuo1 zi5", pos="N", translation="table"),
        _question("W2", "椅子", "easy", pinyin="yi3 zi5", pos="N", translation="chair"),
        _question("W2", "椅子", "medium", pinyin="yi3 zi5", pos="N", translation="chair"),
        _question("W2", "椅子", "hard", pinyin="yi3 zi5", pos="N", translation="chair"),
    ]
    story = {
        "id": "lesson-5-room",
        "title": "Room",
        "lesson_number": 5,
        "lesson_sub_order": 1,
        "published": True,
        "frames": [
            {
                "imageUrl": "/uploads/images/missing.png",
                "listenAudioUrl": "/uploads/audio/scene.wav",
                "vocabulary": "桌子, 燈",
                "vocabularyPinyin": "zhuo1 zi5, deng1",
                "vocabularyPos": "N, N",
                "vocabularyTranslation": "desk, lamp",
            },
            {
                "imageUrl": "",
                "listenAudioUrl": "",
                "vocabulary": "桌子",
                "vocabularyAudioUrls": json.dumps(["/uploads/audio/word.wav"]),
            },
        ],
        "story_vocabulary": None,
        "vocab_assessment": assessment,
        "conversation_turns": [
            {"id": "system-1", "speaker": "system", "text": "你好", "audioUrl": ""}
        ],
    }

    report = build_content_inventory(
        [story], upload_dir=uploads, generated_at="2026-09-24T00:00:00+00:00"
    )

    assert {
        "missing_round_question",
        "speaking_word_missing_canonical_bank",
        "quiz_word_missing_speaking",
        "conflicting_vocabulary_metadata",
        "broken_image",
        "reference_audio_without_source_audio",
        "conversation_missing_character_audio",
        "orphan_media_file",
    } <= _codes(report)
    assert report["readOnly"] is True
    assert report["summary"]["stories"] == 1
    assert report["summary"]["orphanFiles"] == 1
    assert report["media"]["orphanFiles"][0]["url"] == "/uploads/images/orphan.png"
    assert report["lessons"][0]["sources"]["canonicalVocabulary"] == "custom_stories.vocab_assessment"


def test_student_evidence_references_are_separate_and_not_orphans(tmp_path):
    uploads = tmp_path / "uploads"
    (uploads / "audio").mkdir(parents=True)
    (uploads / "audio" / "attempt.wav").write_bytes(b"attempt")
    (uploads / "audio" / "final.wav").write_bytes(b"final")

    report = build_content_inventory(
        [],
        upload_dir=uploads,
        audio_records=[{"id": "attempt-1", "audio_url": "/uploads/audio/attempt.wav"}],
        story_submissions=[
            {"id": "submission-1", "concatenated_audio_url": "/uploads/audio/final.wav", "scenes": []}
        ],
        generated_at="2026-09-24T00:00:00+00:00",
    )

    assert report["summary"]["mediaByDomain"] == {"student_evidence": 2}
    assert report["summary"]["orphanFiles"] == 0
    assert {item["ownerType"] for item in report["media"]["references"]} == {
        "audio_record",
        "story_submission",
    }


@pytest.fixture()
def content_inventory_api(monkeypatch):
    expected = {"readOnly": True, "summary": {"stories": 0}}
    monkeypatch.setattr(
        admin,
        "build_content_inventory_from_database",
        lambda *, upload_dir: expected,
    )
    app = FastAPI()
    app.include_router(admin.router)
    with TestClient(app) as client:
        yield client, expected


def test_content_inventory_endpoint_is_admin_only(content_inventory_api):
    client, expected = content_inventory_api
    assert client.get("/api/admin/content-inventory").status_code == 401

    client.cookies.set(auth.ROLE_COOKIE_NAMES["teacher"], auth.issue_token("teacher", "teacher-1"))
    assert client.get("/api/admin/content-inventory").status_code in (401, 403)

    client.cookies.clear()
    client.cookies.set(auth.ROLE_COOKIE_NAMES["admin"], auth.issue_token("admin", "admin"))
    response = client.get("/api/admin/content-inventory")
    assert response.status_code == 200
    assert response.json() == expected
