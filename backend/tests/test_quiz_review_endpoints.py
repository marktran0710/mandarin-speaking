"""POST /api/custom-stories/{id}/quiz/validate and .../quiz/approve — the
teacher-triggered adversarial validation step and the publish gate that
writes quiz_approved_snapshot. The chat callable is monkeypatched so these
run with scripted responses, no network or API keys."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import main  # noqa: F401 - must import before routers.quiz_review to avoid a circular import
import routers.quiz_review as quiz_review


def scripted_chat(*responses):
    queue = list(responses)

    async def chat(system, user):
        return queue.pop(0) if queue else json.dumps({"results": []})

    return chat


def fake_make_chat(*responses):
    def make_chat(groq_key, gemini_key):
        return scripted_chat(*responses)

    return make_chat


def solver_row(n, choice, also_correct=None):
    return {"n": n, "choice": choice, "alsoCorrect": also_correct or [], "confidence": "high", "why": "ok"}


def judge_row(n, verdict, reason="ok", replace=None):
    return {"n": n, "verdict": verdict, "replace": replace or [], "reason": reason}


@pytest.fixture()
def story_client(client):
    story = {
        "id": "story-review-x",
        "title": "測試故事",
        "learningGoal": "goal",
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


class TestValidate:
    def test_clean_item_passes_through(self, story_client, monkeypatch):
        monkeypatch.setattr(
            quiz_review,
            "make_chat",
            fake_make_chat(
                json.dumps({"results": [solver_row(1, "to know")]}),
                json.dumps({"results": [judge_row(1, "pass")]}),
            ),
        )
        response = story_client.post(
            "/api/custom-stories/story-review-x/quiz/validate",
            json={"words": WORDS, "exclusions": []},
        )
        assert response.status_code == 200
        results = response.json()["results"]
        assert len(results) == 1
        assert results[0]["status"] == "clean"
        # Internal pipeline kind "translation" is exposed as "distractors" —
        # the same pool name TeacherQuizReviewPage's trash button already uses.
        assert results[0]["kind"] == "translation"
        assert results[0]["word"] == "知道"

    def test_rejected_item_is_suspicious_with_reason(self, story_client, monkeypatch):
        monkeypatch.setattr(
            quiz_review,
            "make_chat",
            fake_make_chat(
                json.dumps({"results": [solver_row(1, "to see", also_correct=["to know"])]}),
                json.dumps({"results": [judge_row(1, "reject", reason="second correct answer")]}),
            ),
        )
        response = story_client.post(
            "/api/custom-stories/story-review-x/quiz/validate",
            json={"words": WORDS, "exclusions": []},
        )
        results = response.json()["results"]
        assert results[0]["status"] == "suspicious"
        assert results[0]["reason"] == "second correct answer"

    def test_no_auto_repair_even_on_repair_verdict(self, story_client, monkeypatch):
        """User decision: Validate only labels, never auto-fixes — a
        "repair" verdict must still surface as suspicious, not be silently
        patched and reported clean."""
        monkeypatch.setattr(
            quiz_review,
            "make_chat",
            fake_make_chat(
                json.dumps({"results": [solver_row(1, "to see", also_correct=["to know"])]}),
                json.dumps({"results": [judge_row(1, "repair", replace=["to see"])]}),
            ),
        )
        response = story_client.post(
            "/api/custom-stories/story-review-x/quiz/validate",
            json={"words": WORDS, "exclusions": []},
        )
        results = response.json()["results"]
        assert results[0]["status"] == "suspicious"

    def test_excluded_pool_still_checks_the_teacher_authored_answer(self, story_client, monkeypatch):
        monkeypatch.setattr(
            quiz_review,
            "make_chat",
            fake_make_chat(
                json.dumps({"results": [solver_row(1, "to know")]}),
                json.dumps({"results": [judge_row(1, "pass")]}),
            ),
        )
        response = story_client.post(
            "/api/custom-stories/story-review-x/quiz/validate",
            json={
                "words": WORDS,
                "exclusions": [{"word": "知道", "kind": "distractors"}],
            },
        )
        assert response.json()["results"][0]["kind"] == "translation"
        assert response.json()["results"][0]["status"] == "clean"

    def test_no_candidates_skips_llm_entirely(self, story_client, monkeypatch):
        calls = []
        monkeypatch.setattr(
            quiz_review,
            "make_chat",
            lambda groq, gem: calls.append(1) or scripted_chat(),
        )
        response = story_client.post(
            "/api/custom-stories/story-review-x/quiz/validate",
            json={"words": [], "exclusions": []},
        )
        assert response.json()["results"] == []
        assert calls == []


class TestApprove:
    def test_approve_writes_snapshot(self, story_client, monkeypatch):
        monkeypatch.setattr(
            quiz_review,
            "make_chat",
            fake_make_chat(
                json.dumps({"results": [solver_row(1, "to know")]}),
                json.dumps({"results": [judge_row(1, "pass")]}),
            ),
        )
        response = story_client.post(
            "/api/custom-stories/story-review-x/quiz/approve",
            json={"level": "easy", "material": WORDS},
        )
        assert response.status_code == 200
        stories = story_client.get("/api/custom-stories").json()
        story = next(s for s in stories if s["id"] == "story-review-x")
        assert story["quizApprovedSnapshot"]["easy"][0]["word"] == "知道"

    def test_approving_one_tier_leaves_another_tier_untouched(self, story_client, monkeypatch):
        monkeypatch.setattr(
            quiz_review,
            "make_chat",
            fake_make_chat(
                json.dumps({"results": [solver_row(1, "to know")]}),
                json.dumps({"results": [judge_row(1, "pass")]}),
            ),
        )
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

    def test_approve_rejects_a_suspicious_item(self, story_client, monkeypatch):
        monkeypatch.setattr(
            quiz_review,
            "make_chat",
            fake_make_chat(
                json.dumps({"results": [solver_row(1, "to see", also_correct=["to know"])]}),
                json.dumps({"results": [judge_row(1, "reject", reason="second correct answer")]}),
            ),
        )
        response = story_client.post(
            "/api/custom-stories/story-review-x/quiz/approve",
            json={"level": "easy", "material": WORDS},
        )
        assert response.status_code == 422
        assert "second correct answer" in response.json()["detail"]
