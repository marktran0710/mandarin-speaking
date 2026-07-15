"""Confirms the Medium/Hard tier fields round-trip through the
custom-stories API instead of being silently dropped by the Pydantic model."""


def test_medium_and_hard_tier_fields_round_trip(client):
    story = {
        "id": "test-level-tiers-story",
        "title": "Level Tiers Test",
        "learningGoal": "Check easy/medium/hard tiers persist",
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
        "narrativeMode": "describe",
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
