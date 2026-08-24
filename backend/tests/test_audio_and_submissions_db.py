"""Audio records and story submissions round-tripping through PostgreSQL,
including the JSONB praat_metrics / scenes / story_feedback columns."""
import contextlib

from conftest import login_new_client

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


def test_audio_record_round_trips_with_praat_metrics(logged_in_student):
    client, student = logged_in_student
    assert client.post("/api/audio-records", json=AUDIO_RECORD).status_code == 200
    records = client.get("/api/audio-records").json()
    saved = next(r for r in records if r["id"] == "rec-1")
    assert saved["studentId"] == student["id"]
    assert saved["transcription"] == "這是我的房間。"
    assert saved["praatMetrics"] == {"toneAccuracy": 0.82, "pauseCount": 3}


def test_audio_record_resave_updates_in_place(logged_in_student):
    client, _ = logged_in_student
    client.post("/api/audio-records", json=AUDIO_RECORD)
    client.post("/api/audio-records", json={**AUDIO_RECORD, "transcription": "改過了"})
    matching = [r for r in client.get("/api/audio-records").json() if r["id"] == "rec-1"]
    assert len(matching) == 1
    assert matching[0]["transcription"] == "改過了"


def test_delete_audio_record(logged_in_student, logged_in_teacher):
    student_client, _ = logged_in_student
    teacher_client, _ = logged_in_teacher
    student_client.post("/api/audio-records", json=AUDIO_RECORD)
    assert teacher_client.delete("/api/audio-records/rec-1").json() == {"ok": True}
    assert [r for r in student_client.get("/api/audio-records").json() if r["id"] == "rec-1"] == []


def test_audio_records_can_be_filtered_by_student_and_topic():
    with contextlib.ExitStack() as stack:
        student1_client, student1 = login_new_client(stack, "Student One", "student")
        student2_client, _ = login_new_client(stack, "Student Two", "student")
        teacher_client, _ = login_new_client(stack, "Reviewer", "teacher", password="teach123")

        student1_client.post("/api/audio-records", json=AUDIO_RECORD)
        student1_client.post(
            "/api/audio-records",
            json={**AUDIO_RECORD, "id": "rec-other-topic", "topicId": "other-topic"},
        )
        student2_client.post(
            "/api/audio-records",
            json={**AUDIO_RECORD, "id": "rec-other-student"},
        )

        records = teacher_client.get(
            "/api/audio-records",
            params={"student_id": student1["id"], "topic_id": "teacher-story-1"},
        ).json()

    assert [record["id"] for record in records] == ["rec-1"]


def test_story_submission_round_trips_with_scenes(logged_in_student):
    client, student = logged_in_student
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
    assert response.json()["studentId"] == student["id"]
    assert [s["sceneIndex"] for s in response.json()["scenes"]] == [0, 1]

    listed = client.get("/api/story-submissions", params={"story_id": "teacher-story-1"}).json()
    saved = next(s for s in listed if s["id"] == "sub-1")
    assert [s["sceneIndex"] for s in saved["scenes"]] == [0, 1]
    assert saved["scenes"][0]["transcription"] == "這是我的房間。"


def test_story_submissions_filter_by_story_id(logged_in_teacher):
    client, _ = logged_in_teacher
    assert client.get("/api/story-submissions", params={"story_id": "nothing"}).json() == []


def test_story_submissions_requires_login(anonymous_client):
    assert anonymous_client.get("/api/story-submissions").status_code == 401


def test_story_submission_round_trips_self_eval(logged_in_student):
    client, _ = logged_in_student
    submission = {
        "id": "sub-self-eval",
        "storyId": "teacher-story-1",
        "storyTitle": "我的房間",
        "studentName": "Mai",
        "submittedAt": "2026-07-26T08:00:00Z",
        "scenes": [
            {"sceneIndex": 0, "transcription": "這是我的房間。", "audioUrl": "",
             "toneAccuracy": 80.0, "fluencyScore": 70.0, "pronScore": 75.0,
             "selfEvalContent": "good", "selfEvalPronunciation": "ok"},
            # A scene the student skipped the self-eval prompt for.
            {"sceneIndex": 1, "transcription": "房間裡有一張床。", "audioUrl": "",
             "toneAccuracy": 70.0, "fluencyScore": 60.0, "pronScore": 65.0},
        ],
    }
    response = client.post("/api/story-submissions", json=submission)
    assert response.status_code == 200
    scenes = sorted(response.json()["scenes"], key=lambda s: s["sceneIndex"])
    assert scenes[0]["selfEvalContent"] == "good"
    assert scenes[0]["selfEvalPronunciation"] == "ok"
    assert scenes[1]["selfEvalContent"] is None
    assert scenes[1]["selfEvalPronunciation"] is None
