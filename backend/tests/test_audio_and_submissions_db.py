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


def test_teacher_cannot_delete_audio_record(logged_in_student, logged_in_teacher):
    student_client, _ = logged_in_student
    teacher_client, _ = logged_in_teacher
    student_client.post("/api/audio-records", json=AUDIO_RECORD)
    assert teacher_client.delete("/api/audio-records/rec-1").status_code == 403
    assert [r for r in student_client.get("/api/audio-records").json() if r["id"] == "rec-1"]


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
            {"sceneIndex": 1, "baseStoryId": "story-family-1", "difficultyLevel": "easy",
             "transcription": "房間裡有一張床。", "audioUrl": "",
             "toneAccuracy": 70.0, "fluencyScore": 60.0, "pronScore": 65.0,
             "pauseCount": 2, "longestPause": 900, "utteranceCount": 2,
             "choppyPauseCount": 0, "articulationRate": 3.1},
            {"sceneIndex": 0, "baseStoryId": "story-family-1", "difficultyLevel": "easy",
             "transcription": "這是我的房間。", "audioUrl": "",
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
    assert response.json()["scenes"][0]["baseStoryId"] == "story-family-1"
    assert response.json()["scenes"][0]["difficultyLevel"] == "easy"

    listed = client.get("/api/story-submissions", params={"story_id": "teacher-story-1"}).json()
    saved = next(s for s in listed if s["id"] == "sub-1")
    assert [s["sceneIndex"] for s in saved["scenes"]] == [0, 1]
    assert saved["scenes"][0]["transcription"] == "這是我的房間。"
    assert saved["scenes"][0]["baseStoryId"] == "story-family-1"
    assert saved["scenes"][0]["difficultyLevel"] == "easy"


def test_story_submissions_can_omit_scenes(logged_in_student):
    client, _ = logged_in_student
    submission = {
        "id": "sub-light",
        "storyId": "light-story",
        "storyTitle": "Light",
        "studentName": "Mai",
        "submittedAt": "2026-07-26T08:00:00Z",
        "scenes": [
            {"sceneIndex": 0, "baseStoryId": "b", "difficultyLevel": "easy",
             "transcription": "你好。", "audioUrl": "",
             "toneAccuracy": 80.0, "fluencyScore": 70.0, "pronScore": 75.0,
             "pauseCount": 1, "longestPause": 400, "utteranceCount": 1,
             "choppyPauseCount": 0, "articulationRate": 3.4},
        ],
    }
    assert client.post("/api/story-submissions", json=submission).status_code == 200

    full = client.get("/api/story-submissions", params={"story_id": "light-story"}).json()
    assert full[0]["scenes"] != []

    light = client.get(
        "/api/story-submissions",
        params={"story_id": "light-story", "include_scenes": "false"},
    ).json()
    assert len(light) == 1
    # Summary fields the roster/pending views rely on are intact...
    assert light[0]["id"] == "sub-light"
    assert light[0]["storyTitle"] == "Light"
    assert light[0]["reviewStatus"] == "pending"
    # ...but the heavy per-scene payload is dropped.
    assert light[0]["scenes"] == []


def test_story_submissions_filter_by_story_id(logged_in_teacher):
    client, _ = logged_in_teacher
    assert client.get("/api/story-submissions", params={"story_id": "nothing"}).json() == []


def test_teacher_submissions_exclude_test_accounts(logged_in_student, logged_in_teacher, admin_client):
    from db import connect_db

    student_client, student = logged_in_student
    student_client.post("/api/story-submissions", json={
        "id": "sub-test-account",
        "storyId": "teacher-story-1",
        "storyTitle": "我的房間",
        "studentName": student["name"],
        "submittedAt": "2026-07-26T08:00:00Z",
        "scenes": [],
    })
    with connect_db() as db:
        db.execute("UPDATE students SET is_test_account = TRUE WHERE id = %s", (student["id"],))

    teacher_client, _ = logged_in_teacher
    teacher_ids = [s["id"] for s in teacher_client.get("/api/story-submissions").json()]
    assert "sub-test-account" not in teacher_ids

    admin_ids = [s["id"] for s in admin_client.get("/api/story-submissions").json()]
    assert "sub-test-account" in admin_ids


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


def _lesson_submission(submission_id: str, scenes: list, submitted_at: str = "2026-09-20T08:00:00Z") -> dict:
    return {
        "id": submission_id,
        "storyId": "lesson-story-1",
        "storyTitle": "我的房間",
        "studentName": "Mai",
        "submittedAt": submitted_at,
        "scenes": scenes,
    }


SPEAKING_SCENE = {"sceneIndex": 0, "transcription": "這是我的房間。", "audioUrl": "", "toneAccuracy": 80.0}
CONVERSATION_TURN = {
    "sceneIndex": 0, "transcription": "我很好。", "audioUrl": "", "toneAccuracy": 70.0,
    "conversationId": "conv-1", "turnId": "t1", "turnIndex": 1, "promptId": "story-1:conversation:t1",
}


def test_resubmitting_a_lesson_overwrites_the_one_submission_and_reopens_review(logged_in_student, logged_in_teacher):
    client, _ = logged_in_student
    teacher_client, _ = logged_in_teacher

    first = client.post("/api/story-submissions", json=_lesson_submission("submission-1", [SPEAKING_SCENE])).json()
    assert first["submissionCount"] == 1
    assert first["practicePath"] == "speaking"
    reviewed = teacher_client.patch(
        f"/api/story-submissions/{first['id']}/review", json={"status": "reviewed", "note": "Nice tones"},
    )
    assert reviewed.json()["reviewStatus"] == "reviewed"

    # A new client id for the same lesson still lands on the same submission.
    second = client.post(
        "/api/story-submissions",
        json=_lesson_submission("submission-2", [CONVERSATION_TURN], "2026-09-21T08:00:00Z"),
    ).json()
    assert second["id"] == first["id"]
    assert second["submissionCount"] == 2
    assert second["reviewStatus"] == "pending"
    assert second["teacherNote"] == "Nice tones"
    assert second["practicePath"] == "conversation"

    listed = client.get("/api/story-submissions", params={"story_id": "lesson-story-1"}).json()
    assert len(listed) == 1
    assert listed[0]["scenes"][0]["transcription"] == "我很好。"


def test_submission_keeps_conversation_turn_identity_and_records_both_paths(logged_in_student):
    client, _ = logged_in_student
    response = client.post(
        "/api/story-submissions", json=_lesson_submission("submission-both", [SPEAKING_SCENE, CONVERSATION_TURN]),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["practicePath"] == "both"
    turn = next(scene for scene in body["scenes"] if scene.get("turnId"))
    assert turn["conversationId"] == "conv-1"
    assert turn["turnIndex"] == 1
    assert turn["promptId"] == "story-1:conversation:t1"


def test_submission_records_each_quiz_rounds_latest_score(logged_in_student):
    client, _ = logged_in_student
    body = client.post("/api/story-submissions", json=_lesson_submission("submission-quiz", [SPEAKING_SCENE])).json()
    # No finished rounds yet: every round is present and unfinished.
    assert set(body["quizScores"]) == {"tier1", "tier2", "tier3"}
    assert body["quizScores"]["tier1"]["finished"] is False
    assert body["quizScores"]["tier1"]["score"] is None
