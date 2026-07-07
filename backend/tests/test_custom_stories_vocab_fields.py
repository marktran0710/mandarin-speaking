"""Confirms vocabularyPos/vocabularyTranslation round-trip through the
custom-stories API instead of being silently dropped by the Pydantic model."""


def test_vocabulary_pos_and_translation_round_trip(client):
    story = {
        "id": "test-vocab-fields-story",
        "title": "Vocab Fields Test",
        "learningGoal": "Check pos/translation persist",
        "level": "Beginner speaking",
        "frames": [
            {
                "imageUrl": "",
                "prompt": "Describe the picture.",
                "vocabulary": "餐廳, 吃",
                "vocabularyPinyin": "cāntīng, chī",
                "vocabularyPos": "N, V",
                "vocabularyTranslation": "restaurant, to eat",
            }
        ],
        "narrativeMode": "describe",
    }

    post_response = client.post("/api/custom-stories", json=story)
    assert post_response.status_code == 200
    saved_frame = post_response.json()["frames"][0]
    assert saved_frame["vocabularyPos"] == "N, V"
    assert saved_frame["vocabularyTranslation"] == "restaurant, to eat"

    get_response = client.get("/api/custom-stories")
    assert get_response.status_code == 200
    fetched = next(s for s in get_response.json() if s["id"] == "test-vocab-fields-story")
    assert fetched["frames"][0]["vocabularyPos"] == "N, V"
    assert fetched["frames"][0]["vocabularyTranslation"] == "restaurant, to eat"

    client.delete("/api/custom-stories/test-vocab-fields-story")
