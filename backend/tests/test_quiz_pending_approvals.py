"""PUT /api/custom-stories/{id}/quiz-pending-approvals — the Quiz Review
page's opt-in checkbox selections, saved so they survive a page reload
without being a publish action (that's /quiz/approve)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))


@pytest.fixture()
def story_client(client):
    story = {
        "id": "story-pending-x",
        "title": "測試故事",
        "learningGoal": "goal",
        "frames": [{"imageUrl": "u", "prompt": "p", "vocabulary": "知道"}],
        "published": True,
    }
    response = client.post("/api/custom-stories", json=story)
    assert response.status_code in (200, 201)
    return client


class TestQuizPendingApprovals:
    def test_round_trips_through_story_payload(self, story_client):
        approvals = [{"word": "知道", "kind": "cloze", "index": 0}]
        response = story_client.put(
            "/api/custom-stories/story-pending-x/quiz-pending-approvals",
            json={"level": "easy", "approvals": approvals},
        )
        assert response.status_code == 200

        stories = story_client.get("/api/custom-stories").json()
        story = next(s for s in stories if s["id"] == "story-pending-x")
        assert story["quizPendingApprovals"]["easy"] == approvals

    def test_replaces_wholesale_per_tier(self, story_client):
        story_client.put(
            "/api/custom-stories/story-pending-x/quiz-pending-approvals",
            json={"level": "easy", "approvals": [{"word": "知道", "kind": "distractors"}]},
        )
        story_client.put(
            "/api/custom-stories/story-pending-x/quiz-pending-approvals",
            json={"level": "easy", "approvals": [{"word": "知道", "kind": "synonym", "index": 0}]},
        )
        stories = story_client.get("/api/custom-stories").json()
        story = next(s for s in stories if s["id"] == "story-pending-x")
        assert story["quizPendingApprovals"]["easy"] == [
            {"word": "知道", "kind": "synonym", "index": 0}
        ]

    def test_one_tier_never_clobbers_another(self, story_client):
        story_client.put(
            "/api/custom-stories/story-pending-x/quiz-pending-approvals",
            json={"level": "easy", "approvals": [{"word": "知道", "kind": "distractors"}]},
        )
        story_client.put(
            "/api/custom-stories/story-pending-x/quiz-pending-approvals",
            json={"level": "medium", "approvals": []},
        )
        stories = story_client.get("/api/custom-stories").json()
        story = next(s for s in stories if s["id"] == "story-pending-x")
        assert story["quizPendingApprovals"]["easy"] == [{"word": "知道", "kind": "distractors"}]
        assert story["quizPendingApprovals"]["medium"] == []

    def test_unknown_story_404(self, story_client):
        response = story_client.put(
            "/api/custom-stories/nope/quiz-pending-approvals",
            json={"level": "easy", "approvals": []},
        )
        assert response.status_code == 404

    def test_new_story_has_no_pending_approvals(self, story_client):
        stories = story_client.get("/api/custom-stories").json()
        story = next(s for s in stories if s["id"] == "story-pending-x")
        assert story["quizPendingApprovals"] is None
