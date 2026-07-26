"""The four quiz-pool PATCH endpoints grow per-word pools over time. Under
SQLite each call rewrote the entire 34 KB frames blob, so two concurrent
PATCHes on different frames could lose one another's write. jsonb_set
updates only the touched path."""

STORY = {
    "id": "pool-story",
    "title": "我的房間",
    "learningGoal": "g",
    "frames": [
        {"imageUrl": "", "prompt": "這是我的房間。", "vocabulary": "房間, 桌子"},
        {"imageUrl": "", "prompt": "房間裡有一張床。", "vocabulary": "床"},
    ],
    "narrativeMode": "story",
}


def _make_story(client):
    assert client.post("/api/custom-stories", json=STORY).status_code == 200


def _frames(client):
    story = next(
        s for s in client.get("/api/custom-stories").json() if s["id"] == "pool-story"
    )
    return story["frames"]


def test_distractors_are_stored_as_a_json_string_per_word(client):
    import json

    _make_story(client)
    response = client.patch(
        "/api/custom-stories/pool-story/vocabulary-distractors",
        json={"updates": [{"frameIndex": 0, "wordIndex": 0, "distractors": ["廚房", "客廳"]}]},
    )
    assert response.json() == {"ok": True}

    raw = _frames(client)[0]["vocabularyDistractors"]
    # The frontend does JSON.parse() on this field — it must stay a string.
    assert isinstance(raw, str)
    assert json.loads(raw)[0] == ["廚房", "客廳"]


def test_distractors_merge_instead_of_replacing(client):
    import json

    _make_story(client)
    client.patch(
        "/api/custom-stories/pool-story/vocabulary-distractors",
        json={"updates": [{"frameIndex": 0, "wordIndex": 0, "distractors": ["廚房"]}]},
    )
    client.patch(
        "/api/custom-stories/pool-story/vocabulary-distractors",
        json={"updates": [{"frameIndex": 0, "wordIndex": 0, "distractors": ["客廳", "廚房"]}]},
    )
    pool = json.loads(_frames(client)[0]["vocabularyDistractors"])
    assert pool[0] == ["廚房", "客廳"]  # deduped, order preserved


def test_patching_one_frame_leaves_the_other_untouched(client):
    import json

    _make_story(client)
    client.patch(
        "/api/custom-stories/pool-story/vocabulary-distractors",
        json={"updates": [{"frameIndex": 1, "wordIndex": 0, "distractors": ["椅子"]}]},
    )
    client.patch(
        "/api/custom-stories/pool-story/vocabulary-lookalike",
        json={"updates": [{"frameIndex": 0, "wordIndex": 0, "lookalikes": ["房閒"]}]},
    )
    frames = _frames(client)
    assert json.loads(frames[1]["vocabularyDistractors"])[0] == ["椅子"]
    assert json.loads(frames[0]["vocabularyLookalike"])[0] == ["房閒"]
    assert frames[0]["prompt"] == "這是我的房間。"
    assert frames[1]["prompt"] == "房間裡有一張床。"


def test_cloze_candidates_dedupe_by_sentence(client):
    import json

    _make_story(client)
    payload = {
        "updates": [
            {
                "frameIndex": 0,
                "wordIndex": 0,
                "candidates": [
                    {"sentence": "這是我的＿＿。", "distractors": ["廚房"]},
                    {"sentence": "這是我的＿＿。", "distractors": ["客廳"]},
                ],
            }
        ]
    }
    client.patch("/api/custom-stories/pool-story/vocabulary-cloze", json=payload)
    pool = json.loads(_frames(client)[0]["vocabularyCloze"])
    assert len(pool[0]) == 1


def test_synonym_candidates_round_trip(client):
    import json

    _make_story(client)
    client.patch(
        "/api/custom-stories/pool-story/vocabulary-synonym",
        json={
            "updates": [
                {"frameIndex": 0, "wordIndex": 1, "candidates": [
                    {"synonym": "書桌", "distractors": ["椅子", "床"]}
                ]}
            ]
        },
    )
    pool = json.loads(_frames(client)[0]["vocabularySynonym"])
    assert pool[0] == []          # word 0 untouched
    assert pool[1][0]["synonym"] == "書桌"


def test_pool_patch_on_missing_story_is_404(client):
    response = client.patch(
        "/api/custom-stories/nope/vocabulary-distractors",
        json={"updates": [{"frameIndex": 0, "wordIndex": 0, "distractors": ["x"]}]},
    )
    assert response.status_code == 404


def test_quiz_exclusions_replace_wholesale(client):
    _make_story(client)
    first = client.put(
        "/api/custom-stories/pool-story/quiz-exclusions",
        json={"exclusions": [{"word": "房間", "kind": "cloze"}, {"word": "床", "kind": "synonym"}]},
    )
    assert first.json()["quizExclusions"] == [
        {"word": "房間", "kind": "cloze"},
        {"word": "床", "kind": "synonym"},
    ]
    second = client.put(
        "/api/custom-stories/pool-story/quiz-exclusions",
        json={"exclusions": [{"word": "桌子", "kind": "cloze"}]},
    )
    assert second.json()["quizExclusions"] == [{"word": "桌子", "kind": "cloze"}]
