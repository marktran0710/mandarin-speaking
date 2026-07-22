"""Confirms vocabularyLookalike round-trips through the custom-stories API
(instead of being silently dropped by the Pydantic model), and that the
PATCH .../vocabulary-lookalike endpoint grows a word's look-alike pool by
merging in new characters, deduping and capping at 6."""
import json


def _make_story(story_id, vocabulary_lookalike=None):
    frame = {
        "imageUrl": "",
        "prompt": "Describe the picture.",
        "vocabulary": "喝, 買",
        "vocabularyTranslation": "to drink, to buy",
    }
    if vocabulary_lookalike is not None:
        frame["vocabularyLookalike"] = json.dumps(vocabulary_lookalike)
    return {
        "id": story_id,
        "title": "Lookalike Test",
        "learningGoal": "Check look-alikes persist and grow",
        "level": "Beginner speaking",
        "frames": [frame],
        "narrativeMode": "describe",
    }


def test_vocabulary_lookalike_round_trip(client):
    story = _make_story(
        "test-lookalike-round-trip",
        vocabulary_lookalike=[["渴", "喂"], ["賣"]],
    )
    try:
        post_response = client.post("/api/custom-stories", json=story)
        assert post_response.status_code == 200
        saved_frame = post_response.json()["frames"][0]
        assert json.loads(saved_frame["vocabularyLookalike"]) == [["渴", "喂"], ["賣"]]

        get_response = client.get("/api/custom-stories")
        assert get_response.status_code == 200
        fetched = next(
            s for s in get_response.json() if s["id"] == "test-lookalike-round-trip"
        )
        assert json.loads(fetched["frames"][0]["vocabularyLookalike"]) == [["渴", "喂"], ["賣"]]
    finally:
        client.delete("/api/custom-stories/test-lookalike-round-trip")


def test_patch_merges_and_dedupes_new_lookalikes(client):
    story = _make_story(
        "test-lookalike-patch-merge",
        vocabulary_lookalike=[["渴"], []],
    )
    try:
        client.post("/api/custom-stories", json=story)

        response = client.patch(
            "/api/custom-stories/test-lookalike-patch-merge/vocabulary-lookalike",
            json={
                "updates": [
                    # One duplicate (渴), one new (喂).
                    {"frameIndex": 0, "wordIndex": 0, "lookalikes": ["渴", "喂"]},
                ]
            },
        )
        assert response.status_code == 200

        fetched = next(
            s
            for s in client.get("/api/custom-stories").json()
            if s["id"] == "test-lookalike-patch-merge"
        )
        pool = json.loads(fetched["frames"][0]["vocabularyLookalike"])
        assert pool[0] == ["渴", "喂"]
    finally:
        client.delete("/api/custom-stories/test-lookalike-patch-merge")


def test_patch_caps_pool_at_six_per_word(client):
    story = _make_story(
        "test-lookalike-patch-cap",
        vocabulary_lookalike=[["一", "二", "三", "四", "五"], []],
    )
    try:
        client.post("/api/custom-stories", json=story)

        response = client.patch(
            "/api/custom-stories/test-lookalike-patch-cap/vocabulary-lookalike",
            json={
                "updates": [
                    {"frameIndex": 0, "wordIndex": 0, "lookalikes": ["六", "七", "八"]},
                ]
            },
        )
        assert response.status_code == 200

        fetched = next(
            s
            for s in client.get("/api/custom-stories").json()
            if s["id"] == "test-lookalike-patch-cap"
        )
        pool = json.loads(fetched["frames"][0]["vocabularyLookalike"])
        assert pool[0] == ["一", "二", "三", "四", "五", "六"]
    finally:
        client.delete("/api/custom-stories/test-lookalike-patch-cap")


def test_patch_unknown_story_returns_404(client):
    response = client.patch(
        "/api/custom-stories/does-not-exist/vocabulary-lookalike",
        json={"updates": [{"frameIndex": 0, "wordIndex": 0, "lookalikes": ["x"]}]},
    )
    assert response.status_code == 404
