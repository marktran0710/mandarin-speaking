"""PUT /api/custom-stories/{id}/quiz-question — replaces one candidate's
content in place (edit-in-place from Quiz Review), unlike the vocabulary-*
PATCH endpoints which only merge new items into a pool."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))


@pytest.fixture()
def story_client(client):
    story = {
        "id": "story-replace-x",
        "title": "測試故事",
        "frames": [
            {
                "imageUrl": "u",
                "prompt": "p",
                "vocabulary": "知道",
                "vocabularyTranslation": "to know",
                "vocabularyDistractors": json.dumps([["to see", "to hear", "to say"]]),
                "vocabularyCloze": json.dumps(
                    [[{"sentence": "我知道了。", "distractors": ["不知道"]}]]
                ),
                "vocabularySynonym": json.dumps(
                    [[{"synonym": "曉得", "distractors": ["不懂"]}]]
                ),
            }
        ],
        "published": True,
    }
    response = client.post("/api/custom-stories", json=story)
    assert response.status_code in (200, 201)
    return client


def get_frame(story_client):
    stories = story_client.get("/api/custom-stories").json()
    story = next(s for s in stories if s["id"] == "story-replace-x")
    return story["frames"][0]


class TestReplaceDistractors:
    def test_replaces_the_whole_list(self, story_client):
        response = story_client.put(
            "/api/custom-stories/story-replace-x/quiz-question",
            json={
                "frameIndex": 0,
                "wordIndex": 0,
                "kind": "distractors",
                "value": ["to guess", "to wonder", "to ask"],
            },
        )
        assert response.status_code == 200
        frame = get_frame(story_client)
        assert json.loads(frame["vocabularyDistractors"]) == [
            ["to guess", "to wonder", "to ask"]
        ]

    def test_rejects_a_non_string_list(self, story_client):
        response = story_client.put(
            "/api/custom-stories/story-replace-x/quiz-question",
            json={"frameIndex": 0, "wordIndex": 0, "kind": "distractors", "value": [1, 2]},
        )
        assert response.status_code == 422


class TestReplaceCloze:
    def test_replaces_one_candidate_at_its_index(self, story_client):
        response = story_client.put(
            "/api/custom-stories/story-replace-x/quiz-question",
            json={
                "frameIndex": 0,
                "wordIndex": 0,
                "kind": "cloze",
                "poolIndex": 0,
                "value": {"sentence": "他不知道這件事。", "distractors": ["認識"]},
            },
        )
        assert response.status_code == 200
        frame = get_frame(story_client)
        assert json.loads(frame["vocabularyCloze"]) == [
            [{"sentence": "他不知道這件事。", "distractors": ["認識"]}]
        ]

    def test_missing_pool_index_is_rejected(self, story_client):
        response = story_client.put(
            "/api/custom-stories/story-replace-x/quiz-question",
            json={
                "frameIndex": 0,
                "wordIndex": 0,
                "kind": "cloze",
                "value": {"sentence": "x", "distractors": ["y"]},
            },
        )
        assert response.status_code == 404

    def test_out_of_range_pool_index_404s(self, story_client):
        response = story_client.put(
            "/api/custom-stories/story-replace-x/quiz-question",
            json={
                "frameIndex": 0,
                "wordIndex": 0,
                "kind": "cloze",
                "poolIndex": 5,
                "value": {"sentence": "x", "distractors": ["y"]},
            },
        )
        assert response.status_code == 404


class TestReplaceSynonym:
    def test_replaces_one_candidate_at_its_index(self, story_client):
        response = story_client.put(
            "/api/custom-stories/story-replace-x/quiz-question",
            json={
                "frameIndex": 0,
                "wordIndex": 0,
                "kind": "synonym",
                "poolIndex": 0,
                "value": {"synonym": "明白", "distractors": ["糊塗"]},
            },
        )
        assert response.status_code == 200
        frame = get_frame(story_client)
        assert json.loads(frame["vocabularySynonym"]) == [
            [{"synonym": "明白", "distractors": ["糊塗"]}]
        ]

    def test_wrong_shape_is_rejected(self, story_client):
        response = story_client.put(
            "/api/custom-stories/story-replace-x/quiz-question",
            json={
                "frameIndex": 0,
                "wordIndex": 0,
                "kind": "synonym",
                "poolIndex": 0,
                "value": {"sentence": "wrong key for synonym", "distractors": []},
            },
        )
        assert response.status_code == 422


class TestReplaceTranslation:
    def test_replaces_the_correct_answer(self, story_client):
        response = story_client.put(
            "/api/custom-stories/story-replace-x/quiz-question",
            json={
                "frameIndex": 0,
                "wordIndex": 0,
                "kind": "translation",
                "value": "to understand",
            },
        )
        assert response.status_code == 200
        assert get_frame(story_client)["vocabularyTranslation"] == "to understand"

    def test_rejects_an_empty_correct_answer(self, story_client):
        response = story_client.put(
            "/api/custom-stories/story-replace-x/quiz-question",
            json={"frameIndex": 0, "wordIndex": 0, "kind": "translation", "value": "  "},
        )
        assert response.status_code == 422


def test_unknown_frame_404s(story_client):
    response = story_client.put(
        "/api/custom-stories/story-replace-x/quiz-question",
        json={"frameIndex": 9, "wordIndex": 0, "kind": "distractors", "value": ["a", "b", "c"]},
    )
    assert response.status_code == 404
