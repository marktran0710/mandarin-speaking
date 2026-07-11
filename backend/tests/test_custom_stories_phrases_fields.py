"""Confirms phrases/phrasesTranslation round-trip through the
custom-stories API instead of being silently dropped by the Pydantic model."""


def test_phrases_and_translation_round_trip(client):
    story = {
        "id": "test-phrases-fields-story",
        "title": "Phrases Fields Test",
        "learningGoal": "Check phrases persist",
        "level": "Beginner speaking",
        "frames": [
            {
                "imageUrl": "",
                "prompt": "Describe the picture.",
                "vocabulary": "餐廳, 吃",
                "phrases": "我想吃飯, 這是餐廳",
                "phrasesTranslation": "I want to eat, This is a restaurant",
            }
        ],
        "narrativeMode": "describe",
    }

    post_response = client.post("/api/custom-stories", json=story)
    assert post_response.status_code == 200
    saved_frame = post_response.json()["frames"][0]
    assert saved_frame["phrases"] == "我想吃飯, 這是餐廳"
    assert saved_frame["phrasesTranslation"] == "I want to eat, This is a restaurant"

    get_response = client.get("/api/custom-stories")
    assert get_response.status_code == 200
    fetched = next(s for s in get_response.json() if s["id"] == "test-phrases-fields-story")
    assert fetched["frames"][0]["phrases"] == "我想吃飯, 這是餐廳"
    assert fetched["frames"][0]["phrasesTranslation"] == "I want to eat, This is a restaurant"

    client.delete("/api/custom-stories/test-phrases-fields-story")
