"""The admin account is the sole author of canonical learning content."""


STORY = {
    "id": "admin-only-story",
    "title": "Admin-owned story",
    "frames": [{"imageUrl": "", "prompt": "Describe the picture.", "vocabulary": ""}],
}


def test_teacher_cannot_create_or_delete_canonical_story(logged_in_teacher):
    client, _ = logged_in_teacher

    assert client.post("/api/custom-stories", json=STORY).status_code == 403
    assert client.delete("/api/custom-stories/admin-only-story").status_code == 403


def test_admin_can_create_and_delete_canonical_story(admin_client):
    assert admin_client.post("/api/custom-stories", json=STORY).status_code == 200
    assert admin_client.delete("/api/custom-stories/admin-only-story").status_code == 200


def test_admin_content_bank_reload_is_admin_scoped(admin_client, logged_in_teacher):
    assert admin_client.post("/api/custom-stories", json=STORY).status_code == 200
    response = admin_client.get("/api/admin/content-bank")
    assert response.status_code == 200
    assert any(story["id"] == STORY["id"] for story in response.json())

    teacher_client, _ = logged_in_teacher
    assert teacher_client.get("/api/admin/content-bank").status_code == 403
    assert admin_client.delete("/api/custom-stories/admin-only-story").status_code == 200


def test_teacher_cannot_use_admin_story_media_tools(logged_in_teacher):
    client, _ = logged_in_teacher

    assert client.get(
        "/api/inline-media", params={"url": "/uploads/not-a-real-file.png"}
    ).status_code == 403
    assert client.post(
        "/api/generate-story-images",
        json={"situation": "A student asks for help at the station."},
    ).status_code == 403
