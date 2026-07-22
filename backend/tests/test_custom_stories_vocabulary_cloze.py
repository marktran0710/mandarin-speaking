"""Confirms vocabularyCloze round-trips through the custom-stories API, and
that the PATCH .../vocabulary-cloze endpoint grows a word's cloze-candidate
pool by merging in new {sentence, distractors} entries, deduping by sentence
text and capping at MAX_VOCAB_CLOZE_PER_WORD (4)."""
import json


def _make_story(story_id, vocabulary_cloze=None):
    frame = {
        "imageUrl": "",
        "prompt": "Describe the picture.",
        "vocabulary": "餐廳, 吃",
        "vocabularyTranslation": "restaurant, to eat",
    }
    if vocabulary_cloze is not None:
        frame["vocabularyCloze"] = json.dumps(vocabulary_cloze)
    return {
        "id": story_id,
        "title": "Cloze Test",
        "learningGoal": "Check cloze candidates persist and grow",
        "level": "Beginner speaking",
        "frames": [frame],
        "narrativeMode": "describe",
    }


def test_vocabulary_cloze_round_trip(client):
    story = _make_story(
        "test-cloze-round-trip",
        vocabulary_cloze=[
            [{"sentence": "我在餐廳吃飯。", "distractors": ["教室", "公園"]}],
            [],
        ],
    )
    try:
        post_response = client.post("/api/custom-stories", json=story)
        assert post_response.status_code == 200
        saved_frame = post_response.json()["frames"][0]
        assert json.loads(saved_frame["vocabularyCloze"]) == [
            [{"sentence": "我在餐廳吃飯。", "distractors": ["教室", "公園"]}],
            [],
        ]

        get_response = client.get("/api/custom-stories")
        assert get_response.status_code == 200
        fetched = next(s for s in get_response.json() if s["id"] == "test-cloze-round-trip")
        assert json.loads(fetched["frames"][0]["vocabularyCloze"])[0][0]["sentence"] == "我在餐廳吃飯。"
    finally:
        client.delete("/api/custom-stories/test-cloze-round-trip")


def test_patch_merges_and_dedupes_new_cloze_candidates(client):
    story = _make_story(
        "test-cloze-patch-merge",
        vocabulary_cloze=[
            [{"sentence": "我在餐廳吃飯。", "distractors": ["教室", "公園"]}],
            [],
        ],
    )
    try:
        client.post("/api/custom-stories", json=story)

        response = client.patch(
            "/api/custom-stories/test-cloze-patch-merge/vocabulary-cloze",
            json={
                "updates": [
                    {
                        "frameIndex": 0,
                        "wordIndex": 0,
                        "candidates": [
                            # Duplicate sentence -- should be skipped.
                            {"sentence": "我在餐廳吃飯。", "distractors": ["醫院"]},
                            # New sentence -- should be added.
                            {"sentence": "我們今天要去餐廳。", "distractors": ["學校", "公司"]},
                        ],
                    },
                ]
            },
        )
        assert response.status_code == 200

        fetched = next(
            s
            for s in client.get("/api/custom-stories").json()
            if s["id"] == "test-cloze-patch-merge"
        )
        pool = json.loads(fetched["frames"][0]["vocabularyCloze"])
        assert pool[0] == [
            {"sentence": "我在餐廳吃飯。", "distractors": ["教室", "公園"]},
            {"sentence": "我們今天要去餐廳。", "distractors": ["學校", "公司"]},
        ]
    finally:
        client.delete("/api/custom-stories/test-cloze-patch-merge")


def test_patch_caps_pool_at_four_per_word(client):
    story = _make_story(
        "test-cloze-patch-cap",
        vocabulary_cloze=[
            [
                {"sentence": "句子一。", "distractors": ["a"]},
                {"sentence": "句子二。", "distractors": ["b"]},
                {"sentence": "句子三。", "distractors": ["c"]},
                {"sentence": "句子四。", "distractors": ["d"]},
            ],
            [],
        ],
    )
    try:
        client.post("/api/custom-stories", json=story)

        response = client.patch(
            "/api/custom-stories/test-cloze-patch-cap/vocabulary-cloze",
            json={
                "updates": [
                    {
                        "frameIndex": 0,
                        "wordIndex": 0,
                        "candidates": [{"sentence": "句子五。", "distractors": ["e"]}],
                    },
                ]
            },
        )
        assert response.status_code == 200

        fetched = next(
            s
            for s in client.get("/api/custom-stories").json()
            if s["id"] == "test-cloze-patch-cap"
        )
        pool = json.loads(fetched["frames"][0]["vocabularyCloze"])
        assert len(pool[0]) == 4
        assert pool[0][-1]["sentence"] == "句子四。"
    finally:
        client.delete("/api/custom-stories/test-cloze-patch-cap")


def test_patch_unknown_story_returns_404(client):
    response = client.patch(
        "/api/custom-stories/does-not-exist/vocabulary-cloze",
        json={"updates": [{"frameIndex": 0, "wordIndex": 0, "candidates": []}]},
    )
    assert response.status_code == 404
