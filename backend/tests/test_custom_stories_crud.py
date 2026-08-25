"""Materials CRUD against PostgreSQL.

The upsert test is the important one: SQLite's INSERT OR REPLACE is a
DELETE+INSERT, so re-saving a story used to wipe quiz_exclusions (never
listed in the INSERT) and reset created_at, silently reshuffling the
teacher's story list. ON CONFLICT DO UPDATE only touches listed columns.
"""

STORY = {
    "id": "crud-story-1",
    "title": "我的房間",
    "frames": [
        {"imageUrl": "", "prompt": "這是我的房間。", "vocabulary": "房間, 桌子"},
        {"imageUrl": "", "prompt": "房間裡有一張床。", "vocabulary": "床"},
    ],
    "published": True,
    "lessonNumber": 5,
}


def test_create_then_list_round_trips(client):
    assert client.post("/api/custom-stories", json=STORY).status_code == 200

    stories = client.get("/api/custom-stories").json()
    saved = next(s for s in stories if s["id"] == "crud-story-1")
    assert saved["title"] == "我的房間"
    assert saved["published"] is True
    assert saved["lessonNumber"] == 5
    assert len(saved["frames"]) == 2
    assert saved["frames"][1]["prompt"] == "房間裡有一張床。"
    assert saved["quizExclusions"] == []


def test_resave_preserves_quiz_exclusions(client):
    client.post("/api/custom-stories", json=STORY)
    client.put(
        "/api/custom-stories/crud-story-1/quiz-exclusions",
        json={"exclusions": [{"word": "房間", "kind": "cloze"}]},
    )

    # Teacher edits the title and saves again.
    client.post("/api/custom-stories", json={**STORY, "title": "我的新房間"})

    saved = next(
        s for s in client.get("/api/custom-stories").json() if s["id"] == "crud-story-1"
    )
    assert saved["title"] == "我的新房間"
    assert saved["quizExclusions"] == [{"word": "房間", "kind": "cloze"}]


def test_resave_preserves_created_at(client):
    """Under INSERT OR REPLACE a re-save reset created_at, so an edited
    story jumped to the top of the teacher's list. created_at isn't in the
    API payload, so assert it directly against the database."""
    from database import connect_db

    client.post("/api/custom-stories", json=STORY)
    with connect_db() as db:
        before = db.execute(
            "SELECT created_at FROM custom_stories WHERE id = %s", ("crud-story-1",)
        ).fetchone()["created_at"]

    client.post("/api/custom-stories", json={**STORY, "title": "changed"})
    with connect_db() as db:
        after = db.execute(
            "SELECT created_at FROM custom_stories WHERE id = %s", ("crud-story-1",)
        ).fetchone()["created_at"]

    assert after == before


def test_delete_removes_the_story(client):
    client.post("/api/custom-stories", json=STORY)
    assert client.delete("/api/custom-stories/crud-story-1").json() == {"ok": True}
    ids = [s["id"] for s in client.get("/api/custom-stories").json()]
    assert "crud-story-1" not in ids


def test_delete_is_idempotent_for_a_missing_story(client):
    assert client.delete("/api/custom-stories/never-existed").json() == {"ok": True}


def test_list_pagination(client):
    for index in range(3):
        client.post("/api/custom-stories", json={**STORY, "id": f"page-{index}"})
    page = client.get("/api/custom-stories", params={"limit": 2, "skip": 0}).json()
    assert len(page) == 2
