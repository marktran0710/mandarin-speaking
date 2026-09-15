"""Offline route tests. No application startup or database fixtures required."""
import copy
from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import auth
from routers import vocabulary


@pytest.fixture
def story():
    return {"id": "book-story", "title": "Room", "published": True,
            "lesson_number": 5, "lesson_sub_order": 3,
            "frames": [{"vocabulary": "book, , table", "vocabularyPinyin": "shu, , zhuo zi",
                        "vocabularyTranslation": "book, , table", "vocabularyPos": "N, , N",
                        "prompt": "unchanged", "vocabularySynonym": "[[], [], []]"}],
            "quiz_approved_snapshot": {"easy": [{"word": "table", "translation": "old"}]},
            "vocab_assessment": [{"word": "table", "correctAnswer": "old"}],
            "story_vocabulary": {"easy": {"vocabulary": "table"}}}


@pytest.fixture
def api(monkeypatch, story):
    state = copy.deepcopy(story)
    statements = []

    class Database:
        def execute(self, sql, params):
            statements.append(sql)
            if sql.startswith("UPDATE"):
                if "story_vocabulary = jsonb_set" in sql:
                    field, value, _ = params
                    state["story_vocabulary"].setdefault("easy", {})[field] = value
                else:
                    index, field, value, _ = params
                    state["frames"][int(index)][field] = value
            self.result = copy.deepcopy(state) if params[-1] == "book-story" else None
            return self

        def fetchone(self):
            return self.result

    @contextmanager
    def connect():
        yield Database()

    monkeypatch.setattr(vocabulary, "connect_db", connect)
    app = FastAPI()
    app.include_router(vocabulary.router)
    with TestClient(app) as client:
        client.cookies.set(auth.ROLE_COOKIE_NAMES["admin"], auth.issue_token("admin", "admin"))
        yield client, state, statements


def payload(story, **changes):
    return {"frameIndex": 0, "wordIndex": 2, "tier": "easy", "word": "table",
            "expected": vocabulary.effective_columns(story["frames"][0], "easy"),
            "pinyin": "zhuo zi", "translation": "desk", "pos": "N", **changes}


def test_edits_only_metadata_and_preserves_publication(api, story):
    client, state, statements = api
    result = client.patch("/api/custom-stories/book-story/vocabulary-metadata", json=payload(story))
    assert result.status_code == 200
    assert state["frames"][0]["vocabularyTranslation"] == "book, , desk"
    expected = copy.deepcopy(story)
    expected["frames"][0]["vocabularyTranslation"] = "book, , desk"
    assert state == expected
    assert "FOR UPDATE" in statements[0]
    assert result.json()["quizApprovedSnapshot"] == story["quiz_approved_snapshot"]


def test_stale_metadata_is_conflict_with_no_writes(api, story):
    client, state, statements = api
    edit = payload(story)
    state["frames"][0]["vocabularyTranslation"] = "book, , changed elsewhere"
    assert client.patch("/api/custom-stories/book-story/vocabulary-metadata", json=edit).status_code == 409
    assert not any(s.startswith("UPDATE") for s in statements)


def test_edits_story_wide_metadata_used_by_quiz_rounds(api, story):
    client, state, statements = api
    story_wide = state["story_vocabulary"]["easy"]
    edit = {
        "frameIndex": 0, "wordIndex": 0, "storyWide": True, "tier": "easy", "word": "table",
        "expected": vocabulary.effective_columns(story_wide, "easy"),
        "pinyin": "zhuo zi", "translation": "desk", "pos": "N",
    }
    result = client.patch("/api/custom-stories/book-story/vocabulary-metadata", json=edit)
    assert result.status_code == 200
    assert state["story_vocabulary"]["easy"] == {
        "vocabulary": "table", "vocabularyPinyin": "zhuo zi",
        "vocabularyTranslation": "desk", "vocabularyPos": "N",
    }
    assert any("story_vocabulary = jsonb_set" in sql for sql in statements)


@pytest.mark.parametrize("changes,status", [
    ({"word": "different"}, 409), ({"wordIndex": 1}, 409), ({"wordIndex": 8}, 409),
    ({"frameIndex": 8}, 409), ({"wordIndex": -1}, 422), ({"tier": "A2"}, 422),
    ({"tier": "medium"}, 422), ({"tier": "hard"}, 422),
    ({"translation": "desk, table"}, 422), ({"pinyin": " "}, 422), ({"pos": "N\nV"}, 422),
    ({"extra": "no"}, 422),
])
def test_invalid_edits_do_not_write(api, story, changes, status):
    client, _, statements = api
    assert client.patch("/api/custom-stories/book-story/vocabulary-metadata", json=payload(story, **changes)).status_code == status
    assert not any(s.startswith("UPDATE") for s in statements)


def test_missing_story(api, story):
    client, _, _ = api
    assert client.patch("/api/custom-stories/missing/vocabulary-metadata", json=payload(story)).status_code == 404


@pytest.mark.parametrize("role", [None, "student", "teacher"])
def test_only_admin_can_edit(api, story, role):
    client, _, statements = api
    client.cookies.clear()
    if role:
        client.cookies.set(auth.ROLE_COOKIE_NAMES[role], auth.issue_token(role, "test-user"))
    result = client.patch("/api/custom-stories/book-story/vocabulary-metadata", json=payload(story))
    assert result.status_code in (401, 403)
    assert not statements


def test_misaligned_columns_are_rejected(story):
    frame = story["frames"][0]
    frame["vocabularyPinyin"] = "a,b,c,d"
    edit = vocabulary.VocabularyMetadataEdit(**payload(story))
    with pytest.raises(vocabulary.HTTPException) as error:
        vocabulary.metadata_changes(frame, edit)
    assert error.value.status_code == 422
