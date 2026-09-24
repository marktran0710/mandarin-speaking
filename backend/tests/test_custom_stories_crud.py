"""Materials CRUD against PostgreSQL."""

STORY = {
    "id": "crud-story-1",
    "title": "???輸?",
    "frames": [
        {"imageUrl": "", "prompt": "????輸???", "vocabulary": "?輸?, 獢?"},
        {"imageUrl": "", "prompt": "?輸?鋆⊥?銝撘萄???", "vocabulary": "摨?"},
    ],
    "storyVocabulary": {
        "easy": {
            "vocabulary": "?輸?, 獢?, 摨?",
            "vocabularyPinyin": "f獺ngji?n, zhu?zi, chu獺ng",
            "vocabularyPos": "N, N, N",
            "vocabularyTranslation": "room, table, bed",
        }
    },
    "storyPhrases": {
        "easy": {
            "phrases": "?冽?ㄐ",
            "phrasesTranslation": "in the room",
        }
    },
    "published": True,
    "lessonNumber": 5,
}


def test_create_then_list_round_trips(admin_client):
    assert admin_client.post("/api/custom-stories", json=STORY).status_code == 200

    stories = admin_client.get("/api/custom-stories").json()
    saved = next(s for s in stories if s["id"] == "crud-story-1")
    assert saved["title"] == "???輸?"
    assert saved["published"] is True
    assert saved["lessonNumber"] == 5
    assert len(saved["frames"]) == 2
    assert saved["frames"][1]["prompt"] == "?輸?鋆⊥?銝撘萄???"
    assert saved["storyVocabulary"] == STORY["storyVocabulary"]
    assert saved["storyPhrases"] == STORY["storyPhrases"]


def test_create_without_story_learning_content_keeps_legacy_shape(admin_client):
    legacy_story = {
        key: value
        for key, value in STORY.items()
        if key not in {"storyVocabulary", "storyPhrases"}
    }
    legacy_story["id"] = "legacy-story"

    assert admin_client.post("/api/custom-stories", json=legacy_story).status_code == 200
    saved = next(
        story for story in admin_client.get("/api/custom-stories").json()
        if story["id"] == "legacy-story"
    )
    assert saved["storyVocabulary"] is None
    assert saved["storyPhrases"] is None


def test_resave_preserves_created_at(admin_client):
    """Under INSERT OR REPLACE a re-save reset created_at, so an edited
    story jumped to the top of the teacher's list. created_at isn't in the
    API payload, so assert it directly against the database."""
    from db import connect_db

    admin_client.post("/api/custom-stories", json=STORY)
    with connect_db() as db:
        before = db.execute(
            "SELECT created_at FROM custom_stories WHERE id = %s", ("crud-story-1",)
        ).fetchone()["created_at"]

    admin_client.post("/api/custom-stories", json={**STORY, "title": "changed"})
    with connect_db() as db:
        after = db.execute(
            "SELECT created_at FROM custom_stories WHERE id = %s", ("crud-story-1",)
        ).fetchone()["created_at"]

    assert after == before


def test_delete_removes_the_story(admin_client):
    admin_client.post("/api/custom-stories", json=STORY)
    assert admin_client.delete("/api/custom-stories/crud-story-1").json() == {"ok": True}
    ids = [s["id"] for s in admin_client.get("/api/custom-stories").json()]
    assert "crud-story-1" not in ids


def test_delete_is_idempotent_for_a_missing_story(admin_client):
    assert admin_client.delete("/api/custom-stories/never-existed").json() == {"ok": True}


def test_list_pagination(admin_client):
    for index in range(3):
        admin_client.post("/api/custom-stories", json={**STORY, "id": f"page-{index}"})
    page = admin_client.get("/api/custom-stories", params={"limit": 2, "skip": 0}).json()
    assert len(page) == 2

