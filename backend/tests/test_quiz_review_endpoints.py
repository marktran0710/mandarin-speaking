"""POST /api/custom-stories/{id}/quiz/approve — the publish gate that writes
quiz_approved_snapshot. Quiz material is entirely teacher-authored (typed or
bulk uploaded); this endpoint only enforces structural integrity, no AI."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import main  # noqa: F401 - must import before routers.quiz_review to avoid a circular import


@pytest.fixture()
def story_client(client):
    story = {
        "id": "story-review-x",
        "title": "測試故事",
        "frames": [{"imageUrl": "u", "prompt": "p", "vocabulary": "知道"}],
        "published": True,
    }
    response = client.post("/api/custom-stories", json=story)
    assert response.status_code in (200, 201)
    return client


WORDS = [
    {
        "word": "知道",
        "translation": "to know",
        "distractors": ["to see", "to hear", "to say"],
        "cloze": [],
        "synonym": [],
    }
]


class TestApprove:
    def test_approve_writes_snapshot(self, story_client):
        response = story_client.post(
            "/api/custom-stories/story-review-x/quiz/approve",
            json={"level": "easy", "material": WORDS},
        )
        assert response.status_code == 200
        stories = story_client.get("/api/custom-stories").json()
        story = next(s for s in stories if s["id"] == "story-review-x")
        assert story["quizApprovedSnapshot"]["easy"][0]["word"] == "知道"

    def test_approving_one_tier_leaves_another_tier_untouched(self, story_client):
        story_client.post(
            "/api/custom-stories/story-review-x/quiz/approve",
            json={"level": "easy", "material": WORDS},
        )
        story_client.post(
            "/api/custom-stories/story-review-x/quiz/approve",
            json={"level": "medium", "material": []},
        )
        stories = story_client.get("/api/custom-stories").json()
        story = next(s for s in stories if s["id"] == "story-review-x")
        assert story["quizApprovedSnapshot"]["easy"][0]["word"] == "知道"
        assert story["quizApprovedSnapshot"]["medium"] == []

    def test_unknown_story_404(self, story_client):
        response = story_client.post(
            "/api/custom-stories/nope/quiz/approve",
            json={"level": "easy", "material": []},
        )
        assert response.status_code == 404

    def test_approve_rejects_an_empty_word(self, story_client):
        response = story_client.post(
            "/api/custom-stories/story-review-x/quiz/approve",
            json={"level": "easy", "material": [{**WORDS[0], "word": "  "}]},
        )
        assert response.status_code == 422
        assert "empty word" in response.json()["detail"]

    def test_approve_rejects_a_repeated_word(self, story_client):
        response = story_client.post(
            "/api/custom-stories/story-review-x/quiz/approve",
            json={"level": "easy", "material": [WORDS[0], WORDS[0]]},
        )
        assert response.status_code == 422
        assert "repeats the word" in response.json()["detail"]

    def test_approve_rejects_a_blank_cloze_sentence(self, story_client):
        material = [{**WORDS[0], "cloze": [{"sentence": "  ", "distractors": ["a"]}]}]
        response = story_client.post(
            "/api/custom-stories/story-review-x/quiz/approve",
            json={"level": "easy", "material": material},
        )
        assert response.status_code == 422
        assert "empty cloze sentence" in response.json()["detail"]

    def test_approve_trims_distractors_to_three(self, story_client):
        material = [{**WORDS[0], "distractors": ["a", "b", "c", "d", "e"]}]
        story_client.post(
            "/api/custom-stories/story-review-x/quiz/approve",
            json={"level": "easy", "material": material},
        )
        stories = story_client.get("/api/custom-stories").json()
        story = next(s for s in stories if s["id"] == "story-review-x")
        assert story["quizApprovedSnapshot"]["easy"][0]["distractors"] == ["a", "b", "c"]
