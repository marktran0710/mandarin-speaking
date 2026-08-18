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
        second = [{"word": "茶", "kind": "distractors"}]
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


class TestQuizMaterialSnapshot:
    """materialSnapshot is keyed by difficulty tier (easy/medium/hard word
    text and pools can differ per tier) — the frontend sends the whole map
    each save, so one tier's save must not clobber another's baseline."""

    def test_snapshot_round_trips(self, story_client):
        snapshot = {
            "easy": [
                {"word": "喝", "translation": "drink", "distractors": ["吃"], "cloze": [], "synonym": []},
            ],
        }
        response = story_client.put(
            "/api/custom-stories/story-quiz-x/quiz-exclusions",
            json={"exclusions": [], "materialSnapshot": snapshot},
        )
        assert response.status_code == 200

        stories = story_client.get("/api/custom-stories").json()
        story = next(s for s in stories if s["id"] == "story-quiz-x")
        assert story["quizMaterialSnapshot"] == snapshot

    def test_omitted_snapshot_leaves_previous_value(self, story_client):
        snapshot = {
            "easy": [{"word": "喝", "translation": "drink", "distractors": [], "cloze": [], "synonym": []}],
        }
        story_client.put(
            "/api/custom-stories/story-quiz-x/quiz-exclusions",
            json={"exclusions": [], "materialSnapshot": snapshot},
        )
        # A later save that marks something bad, without re-sending a
        # snapshot, must not wipe the one already stored.
        story_client.put(
            "/api/custom-stories/story-quiz-x/quiz-exclusions",
            json={"exclusions": [{"word": "喝", "kind": "word"}]},
        )
        stories = story_client.get("/api/custom-stories").json()
        story = next(s for s in stories if s["id"] == "story-quiz-x")
        assert story["quizMaterialSnapshot"] == snapshot

    def test_new_story_has_no_snapshot(self, story_client):
        stories = story_client.get("/api/custom-stories").json()
        story = next(s for s in stories if s["id"] == "story-quiz-x")
        assert story["quizMaterialSnapshot"] is None
