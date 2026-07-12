"""Confirms vocabularyDistractors round-trips through the custom-stories API
(instead of being silently dropped by the Pydantic model), and that the
PATCH .../vocabulary-distractors endpoint grows a word's distractor pool by
merging in new options, deduping case-insensitively and capping at 8."""
import json


def _make_story(story_id, vocabulary_distractors=None):
    frame = {
        "imageUrl": "",
        "prompt": "Describe the picture.",
        "vocabulary": "餐廳, 吃",
        "vocabularyTranslation": "restaurant, to eat",
    }
    if vocabulary_distractors is not None:
        frame["vocabularyDistractors"] = json.dumps(vocabulary_distractors)
    return {
        "id": story_id,
        "title": "Distractors Test",
        "learningGoal": "Check distractors persist and grow",
        "level": "Beginner speaking",
        "frames": [frame],
        "narrativeMode": "describe",
    }


def test_vocabulary_distractors_round_trip(client):
    story = _make_story(
        "test-distractors-round-trip",
        vocabulary_distractors=[["kitchen", "hotel"], ["to drink", "to cook"]],
    )
    try:
        post_response = client.post("/api/custom-stories", json=story)
        assert post_response.status_code == 200
        saved_frame = post_response.json()["frames"][0]
        assert json.loads(saved_frame["vocabularyDistractors"]) == [
            ["kitchen", "hotel"],
            ["to drink", "to cook"],
        ]

        get_response = client.get("/api/custom-stories")
        assert get_response.status_code == 200
        fetched = next(
            s for s in get_response.json() if s["id"] == "test-distractors-round-trip"
        )
        assert json.loads(fetched["frames"][0]["vocabularyDistractors"]) == [
            ["kitchen", "hotel"],
            ["to drink", "to cook"],
        ]
    finally:
        client.delete("/api/custom-stories/test-distractors-round-trip")


def test_patch_merges_and_dedupes_new_distractors(client):
    story = _make_story(
        "test-distractors-patch-merge",
        vocabulary_distractors=[["kitchen", "hotel"], []],
    )
    try:
        client.post("/api/custom-stories", json=story)

        response = client.patch(
            "/api/custom-stories/test-distractors-patch-merge/vocabulary-distractors",
            json={
                "updates": [
                    # "Hotel" (different case) and "cafe" -- one dup, one new.
                    {"frameIndex": 0, "wordIndex": 0, "distractors": ["Hotel", "cafe"]},
                ]
            },
        )
        assert response.status_code == 200

        fetched = next(
            s
            for s in client.get("/api/custom-stories").json()
            if s["id"] == "test-distractors-patch-merge"
        )
        pool = json.loads(fetched["frames"][0]["vocabularyDistractors"])
        assert pool[0] == ["kitchen", "hotel", "cafe"]
    finally:
        client.delete("/api/custom-stories/test-distractors-patch-merge")


def test_patch_caps_pool_at_eight_per_word(client):
    story = _make_story(
        "test-distractors-patch-cap",
        vocabulary_distractors=[["a", "b", "c", "d", "e", "f", "g"], []],
    )
    try:
        client.post("/api/custom-stories", json=story)

        response = client.patch(
            "/api/custom-stories/test-distractors-patch-cap/vocabulary-distractors",
            json={
                "updates": [
                    {"frameIndex": 0, "wordIndex": 0, "distractors": ["h", "i", "j"]},
                ]
            },
        )
        assert response.status_code == 200

        fetched = next(
            s
            for s in client.get("/api/custom-stories").json()
            if s["id"] == "test-distractors-patch-cap"
        )
        pool = json.loads(fetched["frames"][0]["vocabularyDistractors"])
        assert pool[0] == ["a", "b", "c", "d", "e", "f", "g", "h"]
    finally:
        client.delete("/api/custom-stories/test-distractors-patch-cap")


def test_patch_unknown_story_returns_404(client):
    response = client.patch(
        "/api/custom-stories/does-not-exist/vocabulary-distractors",
        json={"updates": [{"frameIndex": 0, "wordIndex": 0, "distractors": ["x"]}]},
    )
    assert response.status_code == 404
