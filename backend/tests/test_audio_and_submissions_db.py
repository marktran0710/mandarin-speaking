"""Audio records and story submissions round-tripping through PostgreSQL,
including the JSONB praat_metrics / scenes / story_feedback columns."""

AUDIO_RECORD = {
    "id": "rec-1",
    "timestamp": "2026-07-26T08:00:00Z",
    "duration": 3200,
    "transcription": "這是我的房間。",
    "model": "whisper",
    "topicId": "teacher-story-1",
    "imageUrl": "/uploads/images/a.png",
    "imageIndex": 0,
    "audioUrl": None,
    "praatMetrics": {"toneAccuracy": 0.82, "pauseCount": 3},
}


def test_audio_record_round_trips_with_praat_metrics(client):
    assert client.post("/api/audio-records", json=AUDIO_RECORD).status_code == 200
    records = client.get("/api/audio-records").json()
    saved = next(r for r in records if r["id"] == "rec-1")
    assert saved["transcription"] == "這是我的房間。"
    assert saved["praatMetrics"] == {"toneAccuracy": 0.82, "pauseCount": 3}


def test_audio_record_resave_updates_in_place(client):
    client.post("/api/audio-records", json=AUDIO_RECORD)
    client.post("/api/audio-records", json={**AUDIO_RECORD, "transcription": "改過了"})
    matching = [r for r in client.get("/api/audio-records").json() if r["id"] == "rec-1"]
    assert len(matching) == 1
    assert matching[0]["transcription"] == "改過了"


def test_delete_audio_record(client):
    client.post("/api/audio-records", json=AUDIO_RECORD)
    assert client.delete("/api/audio-records/rec-1").json() == {"ok": True}
    assert [r for r in client.get("/api/audio-records").json() if r["id"] == "rec-1"] == []


def test_story_submission_round_trips_with_scenes(client):
    submission = {
        "id": "sub-1",
        "storyId": "teacher-story-1",
        "storyTitle": "我的房間",
        "studentName": "Mai",
        "submittedAt": "2026-07-26T08:00:00Z",
        "scenes": [
            {"sceneIndex": 1, "transcription": "房間裡有一張床。", "audioUrl": "",
             "toneAccuracy": 70.0, "fluencyScore": 60.0, "pronScore": 65.0,
             "pauseCount": 2, "longestPause": 900, "utteranceCount": 2,
             "choppyPauseCount": 0, "articulationRate": 3.1},
            {"sceneIndex": 0, "transcription": "這是我的房間。", "audioUrl": "",
             "toneAccuracy": 80.0, "fluencyScore": 70.0, "pronScore": 75.0,
             "pauseCount": 1, "longestPause": 400, "utteranceCount": 1,
             "choppyPauseCount": 0, "articulationRate": 3.4},
        ],
    }
    response = client.post("/api/story-submissions", json=submission)
    assert response.status_code == 200
    # Scenes are stored sorted by sceneIndex regardless of submitted order.
    assert [s["sceneIndex"] for s in response.json()["scenes"]] == [0, 1]

    listed = client.get("/api/story-submissions", params={"story_id": "teacher-story-1"}).json()
    saved = next(s for s in listed if s["id"] == "sub-1")
    assert [s["sceneIndex"] for s in saved["scenes"]] == [0, 1]
    assert saved["scenes"][0]["transcription"] == "這是我的房間。"


def test_story_submissions_filter_by_story_id(client):
    assert client.get("/api/story-submissions", params={"story_id": "nothing"}).json() == []
