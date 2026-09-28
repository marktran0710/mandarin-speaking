import io
import zipfile

from services.content.materials_import import (
    _parse_image_assets,
    _parse_script_rows,
    build_images_template,
    expected_image_names,
)


def test_scripts_parse_utf8_bom_and_quoted_traditional_chinese():
    content = "\ufefflesson,story,scene,script\r\n5,1,1,\"友美，妳這個週末要做什麼？\"\r\n".encode("utf-8")

    rows, issues = _parse_script_rows(content)

    assert issues == []
    assert rows[0]["storyKey"] == "5-1"
    assert rows[0]["script"] == "友美，妳這個週末要做什麼？"


def test_scripts_reject_duplicate_targets_and_out_of_range_codes():
    content = b"lesson,story,scene,script\n5,1,1,one\n5,1,1,two\n9,1,1,bad\n"

    rows, issues = _parse_script_rows(content)

    assert len(rows) == 3
    assert any("duplicate target" in issue for issue in issues)
    assert any("5-1 through 8-3" in issue for issue in issues)


def test_images_accept_direct_files_and_reject_duplicate_story_names():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("assets/5-1.png", b"first")
        archive.writestr("nested/5-1.jpg", b"duplicate")

    assets, issues = _parse_image_assets([("images.zip", buffer.getvalue())])

    assert [asset["storyKey"] for asset in assets] == ["5-1"]
    assert any("duplicate image" in issue for issue in issues)


def test_images_template_lists_all_twelve_names_without_fake_images():
    with zipfile.ZipFile(io.BytesIO(build_images_template())) as archive:
        assert archive.namelist() == ["README.txt"]
        readme = archive.read("README.txt").decode("utf-8")

    assert all(name in readme for name in expected_image_names())


def test_scripts_endpoint_updates_shared_frame_text_and_clears_conversation_override(admin_client):
    story = {
        "id": "materials-script-story-5-1",
        "title": "Lesson 5 story",
        "lessonNumber": 5,
        "lessonSubOrder": 1,
        "published": True,
        "frames": [
            {"imageUrl": "/uploads/images/old.png", "prompt": "old prompt", "vocabulary": "", "suggestedAnswer": "old one", "listenScript": "old one"},
            {"imageUrl": "/uploads/images/old.png", "prompt": "old prompt 2", "vocabulary": "", "suggestedAnswer": "old two", "listenScript": "old two"},
        ],
        "conversationTurns": [{"id": "override", "speaker": "system", "text": "legacy"}],
    }
    assert admin_client.post("/api/custom-stories", json=story).status_code == 200
    csv_content = "\ufefflesson,story,scene,script\r\n5,1,1,\"新句子一\"\r\n5,1,2,\"新句子二\"\r\n".encode("utf-8")

    preview = admin_client.post(
        "/api/admin/materials/scripts/preview",
        files={"file": ("lessons-5-8.csv", csv_content, "text/csv")},
    )
    assert preview.status_code == 200
    assert preview.json()["valid"] is True
    assert len(preview.json()["changes"]) == 2

    confirmed = admin_client.post(
        "/api/admin/materials/scripts/confirm",
        files={"file": ("lessons-5-8.csv", csv_content, "text/csv")},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["alignmentCleared"] == 2
    saved = admin_client.get("/api/custom-stories").json()[0]
    assert saved["conversationTurns"] is None
    assert [frame["suggestedAnswer"] for frame in saved["frames"]] == ["新句子一", "新句子二"]
    assert [frame["listenScript"] for frame in saved["frames"]] == ["新句子一", "新句子二"]


def test_images_endpoint_reuses_one_stored_url_for_every_scene(admin_client, tmp_path, monkeypatch):
    import services.media as media_service

    upload_root = tmp_path / "uploads"
    monkeypatch.setattr(media_service, "UPLOAD_DIR", str(upload_root))
    monkeypatch.setattr(media_service, "IMAGE_UPLOAD_DIR", str(upload_root / "images"))
    story = {
        "id": "materials-image-story-5-2", "title": "Image story", "lessonNumber": 5,
        "lessonSubOrder": 2, "published": False,
        "frames": [
            {"imageUrl": "old-a.png", "prompt": "one", "vocabulary": ""},
            {"imageUrl": "old-b.png", "prompt": "two", "vocabulary": ""},
        ],
    }
    assert admin_client.post("/api/custom-stories", json=story).status_code == 200
    content = b"not-a-real-image-but-a-stored-payload"
    response = admin_client.post(
        "/api/admin/materials/images/confirm",
        files={"file": ("5-2.png", content, "image/png")},
    )
    assert response.status_code == 200
    saved = admin_client.get("/api/custom-stories").json()[0]
    image_urls = {frame["imageUrl"] for frame in saved["frames"]}
    assert len(image_urls) == 1
    stored_url = next(iter(image_urls))
    assert stored_url.startswith("/uploads/images/materials-5-2-")
    assert (upload_root / "images" / stored_url.rsplit("/", 1)[1]).is_file()
