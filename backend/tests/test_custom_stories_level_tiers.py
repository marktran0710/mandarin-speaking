"""Confirms the Medium/Hard tier fields round-trip through the
custom-stories API instead of being silently dropped by the Pydantic model."""
import pytest

# A 1x1 PNG, same bytes used by test_inline_media.py's fixture.
_PNG_DATA_URL = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4"
    "2mP4//8/AwAI/AL+p6c5nQAAAABJRU5ErkJggg=="
)


@pytest.fixture()
def isolated_uploads(tmp_path, monkeypatch):
    """Points UPLOAD_DIR/IMAGE_UPLOAD_DIR at a temp dir so this test's saved
    files don't land in (or get cleaned from) the real uploads folder."""
    import main

    upload_dir = tmp_path / "uploads"
    (upload_dir / "images").mkdir(parents=True)
    monkeypatch.setattr(main, "UPLOAD_DIR", str(upload_dir))
    monkeypatch.setattr(main, "IMAGE_UPLOAD_DIR", str(upload_dir / "images"))
    return upload_dir


def test_medium_and_hard_tier_fields_round_trip(client):
    story = {
        "id": "test-level-tiers-story",
        "title": "Level Tiers Test",
        "level": "Beginner speaking",
        "frames": [
            {
                "imageUrl": "",
                "prompt": "你好嗎？",
                "vocabulary": "你好",
                "promptMedium": "你今天好嗎？",
                "vocabularyMedium": "你好, 今天",
                "promptHard": "你今天過得怎麼樣？",
                "vocabularyHard": "你好, 今天, 怎麼樣",
                "suggestedAnswerMedium": "我今天很好。",
                "suggestedAnswerHard": "我今天過得很不錯。",
            }
        ],
    }

    post_response = client.post("/api/custom-stories", json=story)
    assert post_response.status_code == 200
    saved_frame = post_response.json()["frames"][0]
    assert saved_frame["promptMedium"] == "你今天好嗎？"
    assert saved_frame["vocabularyMedium"] == "你好, 今天"
    assert saved_frame["promptHard"] == "你今天過得怎麼樣？"
    assert saved_frame["vocabularyHard"] == "你好, 今天, 怎麼樣"
    assert saved_frame["suggestedAnswerMedium"] == "我今天很好。"
    assert saved_frame["suggestedAnswerHard"] == "我今天過得很不錯。"

    get_response = client.get("/api/custom-stories")
    assert get_response.status_code == 200
    fetched = next(s for s in get_response.json() if s["id"] == "test-level-tiers-story")
    assert fetched["frames"][0]["promptMedium"] == "你今天好嗎？"
    assert fetched["frames"][0]["promptHard"] == "你今天過得怎麼樣？"

    client.delete("/api/custom-stories/test-level-tiers-story")


def test_each_tier_gets_its_own_uploaded_image(client, isolated_uploads):
    """Root cause this guards against: persist_story_frame_images only ever
    saved/replaced the base imageUrl, so uploading a Medium or Hard picture
    silently did nothing distinct — every tier rendered whatever Easy's
    imageUrl happened to be. Each tier's data: URL must now be saved to its
    own file and the three tiers must end up with three different URLs."""
    story = {
        "id": "test-tiered-images-story",
        "title": "Tiered Images Test",
        "frames": [
            {
                "imageUrl": _PNG_DATA_URL,
                "imageUrlMedium": _PNG_DATA_URL,
                "imageUrlHard": _PNG_DATA_URL,
                "prompt": "你好嗎？",
                "vocabulary": "你好",
            }
        ],
    }

    post_response = client.post("/api/custom-stories", json=story)
    assert post_response.status_code == 200
    frame = post_response.json()["frames"][0]

    for field in ("imageUrl", "imageUrlMedium", "imageUrlHard"):
        assert frame[field].startswith("/uploads/images/")

    # Three distinct files, not the same URL saved three times.
    assert len({frame["imageUrl"], frame["imageUrlMedium"], frame["imageUrlHard"]}) == 3
    for field in ("imageUrl", "imageUrlMedium", "imageUrlHard"):
        relative = frame[field].removeprefix("/uploads/")
        assert (isolated_uploads / relative).exists()

    # Replacing only the Medium image shouldn't touch Easy's or Hard's files.
    old_easy_path = isolated_uploads / frame["imageUrl"].removeprefix("/uploads/")
    old_hard_path = isolated_uploads / frame["imageUrlHard"].removeprefix("/uploads/")
    update = {
        **story,
        "frames": [
            {
                "imageUrl": frame["imageUrl"],
                "imageUrlMedium": _PNG_DATA_URL,
                "imageUrlHard": frame["imageUrlHard"],
                "prompt": "你好嗎？",
                "vocabulary": "你好",
            }
        ],
    }
    update_response = client.post("/api/custom-stories", json=update)
    assert update_response.status_code == 200
    updated_frame = update_response.json()["frames"][0]

    assert updated_frame["imageUrl"] == frame["imageUrl"]
    assert updated_frame["imageUrlHard"] == frame["imageUrlHard"]
    assert updated_frame["imageUrlMedium"] != frame["imageUrlMedium"]
    assert old_easy_path.exists()
    assert old_hard_path.exists()

    client.delete("/api/custom-stories/test-tiered-images-story")
