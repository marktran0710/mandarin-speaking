"""Confirms vocabularySynonym round-trips through the custom-stories API, and
that the PATCH .../vocabulary-synonym endpoint grows a word's synonym-
candidate pool by merging in new {synonym, distractors} entries, deduping by
synonym text and capping at MAX_VOCAB_SYNONYM_PER_WORD (4)."""
import json


def _make_story(story_id, vocabulary_synonym=None):
    frame = {
        "imageUrl": "",
        "prompt": "Describe the picture.",
        "vocabulary": "高興, 吃",
        "vocabularyTranslation": "happy, to eat",
    }
    if vocabulary_synonym is not None:
        frame["vocabularySynonym"] = json.dumps(vocabulary_synonym)
    return {
        "id": story_id,
        "title": "Synonym Test",
        "learningGoal": "Check synonym candidates persist and grow",
        "level": "Beginner speaking",
        "frames": [frame],
        "narrativeMode": "describe",
    }


def test_vocabulary_synonym_round_trip(client):
    story = _make_story(
        "test-synonym-round-trip",
        vocabulary_synonym=[
            [{"synonym": "開心", "distractors": ["生氣", "累"]}],
            [],
        ],
    )
    try:
        post_response = client.post("/api/custom-stories", json=story)
        assert post_response.status_code == 200
        saved_frame = post_response.json()["frames"][0]
        assert json.loads(saved_frame["vocabularySynonym"]) == [
            [{"synonym": "開心", "distractors": ["生氣", "累"]}],
            [],
        ]

        get_response = client.get("/api/custom-stories")
        assert get_response.status_code == 200
        fetched = next(s for s in get_response.json() if s["id"] == "test-synonym-round-trip")
        assert json.loads(fetched["frames"][0]["vocabularySynonym"])[0][0]["synonym"] == "開心"
    finally:
        client.delete("/api/custom-stories/test-synonym-round-trip")


def test_patch_merges_and_dedupes_new_synonym_candidates(client):
    story = _make_story(
        "test-synonym-patch-merge",
        vocabulary_synonym=[
            [{"synonym": "開心", "distractors": ["生氣", "累"]}],
            [],
        ],
    )
    try:
        client.post("/api/custom-stories", json=story)

        response = client.patch(
            "/api/custom-stories/test-synonym-patch-merge/vocabulary-synonym",
            json={
                "updates": [
                    {
                        "frameIndex": 0,
                        "wordIndex": 0,
                        "candidates": [
                            # Duplicate synonym -- should be skipped.
                            {"synonym": "開心", "distractors": ["餓"]},
                            # New synonym -- should be added.
                            {"synonym": "快樂", "distractors": ["生氣", "難過"]},
                        ],
                    },
                ]
            },
        )
        assert response.status_code == 200

        fetched = next(
            s
            for s in client.get("/api/custom-stories").json()
            if s["id"] == "test-synonym-patch-merge"
        )
        pool = json.loads(fetched["frames"][0]["vocabularySynonym"])
        assert pool[0] == [
            {"synonym": "開心", "distractors": ["生氣", "累"]},
            {"synonym": "快樂", "distractors": ["生氣", "難過"]},
        ]
    finally:
        client.delete("/api/custom-stories/test-synonym-patch-merge")


def test_patch_caps_pool_at_four_per_word(client):
    story = _make_story(
        "test-synonym-patch-cap",
        vocabulary_synonym=[
            [
                {"synonym": "同義詞一", "distractors": ["a"]},
                {"synonym": "同義詞二", "distractors": ["b"]},
                {"synonym": "同義詞三", "distractors": ["c"]},
                {"synonym": "同義詞四", "distractors": ["d"]},
            ],
            [],
        ],
    )
    try:
        client.post("/api/custom-stories", json=story)

        response = client.patch(
            "/api/custom-stories/test-synonym-patch-cap/vocabulary-synonym",
            json={
                "updates": [
                    {
                        "frameIndex": 0,
                        "wordIndex": 0,
                        "candidates": [{"synonym": "同義詞五", "distractors": ["e"]}],
                    },
                ]
            },
        )
        assert response.status_code == 200

        fetched = next(
            s
            for s in client.get("/api/custom-stories").json()
            if s["id"] == "test-synonym-patch-cap"
        )
        pool = json.loads(fetched["frames"][0]["vocabularySynonym"])
        assert len(pool[0]) == 4
        assert pool[0][-1]["synonym"] == "同義詞四"
    finally:
        client.delete("/api/custom-stories/test-synonym-patch-cap")


def test_patch_unknown_story_returns_404(client):
    response = client.patch(
        "/api/custom-stories/does-not-exist/vocabulary-synonym",
        json={"updates": [{"frameIndex": 0, "wordIndex": 0, "candidates": []}]},
    )
    assert response.status_code == 404
