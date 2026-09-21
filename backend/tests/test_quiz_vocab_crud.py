"""Admin CRUD tests for the per-word Quiz bank editor."""
import copy
from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import security.auth as auth
from routers import story_quiz_vocabulary, vocabulary


def word_payload(*, target_word="桌子", word_id=None, suffix="one"):
    payload = {
        "targetWord": target_word,
        "pinyin": "zhuōzi",
        "pos": "N",
        "simpleEnglishMeaning": "desk",
        "questions": [
            {"level": "Easy", "prompt": f"Easy {suffix}", "options": ["desk", "book", "door", "bed"],
             "correctAnswer": "desk", "acceptedAnswers": ["desk"], "explanation": "Correct."},
            {"level": "Medium", "prompt": f"Medium {suffix}: 這是___。", "options": ["桌子", "書", "門", "床"],
             "correctAnswer": "桌子", "acceptedAnswers": ["桌子"], "explanation": "Correct."},
            {"level": "Hard", "prompt": f"Hard {suffix}: write desk", "options": [],
             "correctAnswer": "桌子", "acceptedAnswers": ["桌子"], "explanation": "Correct."},
        ],
    }
    if word_id is not None:
        payload["wordId"] = word_id
    return payload


@pytest.fixture
def api():
    state = {
        "id": "book-story", "title": "Room", "frames": [], "published": True,
        "lesson_number": 5, "lesson_sub_order": 3, "story_vocabulary": None,
        "story_phrases": None, "vocab_assessment": [], "quiz_exclusions": [],
        "quiz_material_snapshot": None, "quiz_approved_snapshot": None,
        "quiz_pending_approvals": None, "rubric_scores": None,
    }
    statements = []

    class Database:
        def execute(self, sql, params):
            statements.append(sql)
            if sql.startswith("UPDATE custom_stories SET vocab_assessment"):
                state["vocab_assessment"] = copy.deepcopy(params[0].obj)
            self.result = copy.deepcopy(state) if params[-1] == "book-story" else None
            return self

        def fetchone(self):
            return self.result

    @contextmanager
    def connect():
        yield Database()

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(story_quiz_vocabulary, "connect_db", connect)
    app = FastAPI()
    app.include_router(vocabulary.router)
    with TestClient(app) as client:
        client.cookies.set(auth.ROLE_COOKIE_NAMES["admin"], auth.issue_token("admin", "admin"))
        yield client, state, statements
    monkeypatch.undo()


def test_create_generates_stable_ids_and_only_updates_quiz_bank(api):
    client, state, statements = api
    response = client.post("/api/custom-stories/book-story/quiz-vocabulary", json=word_payload())
    assert response.status_code == 200
    questions = state["vocab_assessment"]
    word_id = questions[0]["wordId"]
    assert word_id.startswith("QUIZ_")
    assert {question["questionId"] for question in questions} == {
        f"{word_id}_EASY", f"{word_id}_MEDIUM", f"{word_id}_HARD"
    }
    assert [question["questionType"] for question in questions] == [
        "basic_meaning_mcq", "context_cloze_mcq", "productive_recall"
    ]
    assert all(question["targetWord"] == "桌子" for question in response.json()["vocabAssessment"])
    assert len([sql for sql in statements if sql.startswith("UPDATE")]) == 1


def test_update_replaces_one_word_and_delete_allows_empty_bank(api):
    client, state, _ = api
    assert client.post("/api/custom-stories/book-story/quiz-vocabulary", json=word_payload(word_id="W1")).status_code == 200
    updated = word_payload(target_word="書", word_id="W1", suffix="two")
    updated["pinyin"] = "shū"
    updated["simpleEnglishMeaning"] = "book"
    updated["questions"][0].update({"options": ["book", "desk", "door", "bed"], "correctAnswer": "book", "acceptedAnswers": ["book"]})
    updated["questions"][1].update({"options": ["書", "桌子", "門", "床"], "correctAnswer": "書", "acceptedAnswers": ["書"]})
    updated["questions"][2].update({"correctAnswer": "書", "acceptedAnswers": ["書"]})
    assert client.put("/api/custom-stories/book-story/quiz-vocabulary/W1", json=updated).status_code == 200
    assert {question["targetWord"] for question in state["vocab_assessment"]} == {"書"}
    response = client.delete("/api/custom-stories/book-story/quiz-vocabulary/W1")
    assert response.status_code == 200
    assert state["vocab_assessment"] == []


def test_stale_revision_is_rejected_for_update_and_delete(api):
    client, state, _ = api
    created = client.post("/api/custom-stories/book-story/quiz-vocabulary", json=word_payload(word_id="W1"))
    assert created.status_code == 200
    stale_revision = created.json()["vocabAssessmentRevision"]

    fresh = word_payload(target_word="bookshelf", word_id="W1", suffix="fresh")
    fresh["expectedRevision"] = stale_revision
    assert client.put("/api/custom-stories/book-story/quiz-vocabulary/W1", json=fresh).status_code == 200

    stale_update = word_payload(target_word="wardrobe", word_id="W1", suffix="stale")
    stale_update["expectedRevision"] = stale_revision
    response = client.put("/api/custom-stories/book-story/quiz-vocabulary/W1", json=stale_update)
    assert response.status_code == 409
    assert {question["targetWord"] for question in state["vocab_assessment"]} == {"bookshelf"}

    response = client.delete(f"/api/custom-stories/book-story/quiz-vocabulary/W1?expectedRevision={stale_revision}")
    assert response.status_code == 409
    assert state["vocab_assessment"]


def test_rejects_duplicate_word_or_prompt_without_writing(api):
    client, state, statements = api
    assert client.post("/api/custom-stories/book-story/quiz-vocabulary", json=word_payload(word_id="W1")).status_code == 200
    updates_before = len([sql for sql in statements if sql.startswith("UPDATE")])
    duplicate_word = word_payload(word_id="W2", suffix="different")
    assert client.post("/api/custom-stories/book-story/quiz-vocabulary", json=duplicate_word).status_code == 422
    duplicate_prompt = word_payload(target_word="書", word_id="W2")
    assert client.post("/api/custom-stories/book-story/quiz-vocabulary", json=duplicate_prompt).status_code == 422
    assert len([sql for sql in statements if sql.startswith("UPDATE")]) == updates_before
    assert {question["wordId"] for question in state["vocab_assessment"]} == {"W1"}


@pytest.mark.parametrize("role", [None, "student", "teacher"])
def test_only_admin_can_change_quiz_bank(api, role):
    client, state, _ = api
    client.cookies.clear()
    if role:
        client.cookies.set(auth.ROLE_COOKIE_NAMES[role], auth.issue_token(role, "person"))
    response = client.post("/api/custom-stories/book-story/quiz-vocabulary", json=word_payload())
    assert response.status_code in (401, 403)
    assert state["vocab_assessment"] == []
