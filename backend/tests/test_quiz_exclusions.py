"""PUT /api/custom-stories/{id}/quiz-exclusions — the teacher review page's
bad-material list. Whole-list replace, persisted on the story row, echoed
back by row_to_custom_story. Runs against the isolated test database."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))


@pytest.fixture()
def story_client(client):
    story = {
        "id": "story-quiz-x",
        "title": "測試故事",
        "learningGoal": "goal",
        "frames": [{"imageUrl": "u", "prompt": "p", "vocabulary": "喝,茶"}],
        "published": True,
    }
    response = client.post("/api/custom-stories", json=story)
    assert response.status_code in (200, 201)
    return client


class TestQuizExclusions:

    def test_round_trips_through_story_payload(self, story_client):
        exclusions = [
            {"word": "友美", "kind": "word"},
            {"word": "知道", "kind": "cloze", "index": 1},
            {"word": "一起", "kind": "synonym", "index": 0},
        ]
        response = story_client.put(
            "/api/custom-stories/story-quiz-x/quiz-exclusions",
            json={"exclusions": exclusions},
        )
        assert response.status_code == 200
        assert response.json()["quizExclusions"] == exclusions

        stories = story_client.get("/api/custom-stories").json()
        story = next(s for s in stories if s["id"] == "story-quiz-x")
        assert story["quizExclusions"] == exclusions

    def test_put_replaces_wholesale(self, story_client):
        first = [{"word": "喝", "kind": "word"}]
        second = [{"word": "茶", "kind": "lookalike"}]
        story_client.put(
            "/api/custom-stories/story-quiz-x/quiz-exclusions",
            json={"exclusions": first},
        )
        story_client.put(
            "/api/custom-stories/story-quiz-x/quiz-exclusions",
            json={"exclusions": second},
        )
        stories = story_client.get("/api/custom-stories").json()
        story = next(s for s in stories if s["id"] == "story-quiz-x")
        assert story["quizExclusions"] == second

    def test_empty_list_clears(self, story_client):
        story_client.put(
            "/api/custom-stories/story-quiz-x/quiz-exclusions",
            json={"exclusions": [{"word": "喝", "kind": "word"}]},
        )
        story_client.put(
            "/api/custom-stories/story-quiz-x/quiz-exclusions",
            json={"exclusions": []},
        )
        stories = story_client.get("/api/custom-stories").json()
        assert (
            next(s for s in stories if s["id"] == "story-quiz-x")["quizExclusions"]
            == []
        )

    def test_unknown_story_404(self, story_client):
        response = story_client.put(
            "/api/custom-stories/nope/quiz-exclusions", json={"exclusions": []}
        )
        assert response.status_code == 404

    def test_bad_kind_rejected(self, story_client):
        response = story_client.put(
            "/api/custom-stories/story-quiz-x/quiz-exclusions",
            json={"exclusions": [{"word": "喝", "kind": "banana"}]},
        )
        assert response.status_code == 422
