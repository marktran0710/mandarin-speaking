"""The student-home overview endpoint bundles submissions, quiz attempts and
audio records for one student in a single request, trimmed to the summary
fields the "My Stories" page reads."""
import contextlib

from conftest import login_new_client

SUBMISSION = {
    "id": "ov-sub-1",
    "storyId": "story-ov-1",
    "storyTitle": "我的房間",
    "studentName": "Overview Kid",
    "submittedAt": "2026-09-06T08:00:00Z",
    "scenes": [
        {"sceneIndex": 0, "transcription": "這是我的房間。", "audioUrl": "",
         "toneAccuracy": 80.0, "fluencyScore": 70.0, "pronScore": 75.0},
    ],
}

ATTEMPT = {
    "id": "ov-attempt-1",
    "storyId": "story-ov-1",
    "studentName": "Overview Kid",
    "mode": "tier1",
    "completedAt": "2026-09-06T08:05:00Z",
    "totalQuestions": 20,
    "correctCount": 15,
    "totalTimeMs": 42000,
    "questionResults": [{"word": "房間", "correct": True, "timeMs": 1200}],
}

AUDIO = {
    "id": "ov-rec-1",
    "timestamp": "2026-09-06T08:10:00Z",
    "duration": 3200,
    "transcription": "這是我的房間。",
    "model": "whisper",
    "topicId": "story-ov-1",
    "imageIndex": 0,
    "audioUrl": None,
    "praatMetrics": {"tone_accuracy": 0.82, "fluency_score": 0.7},
}


def test_overview_bundles_and_trims(logged_in_student):
    client, student = logged_in_student
    assert client.post("/api/story-submissions", json=SUBMISSION).status_code == 200
    assert client.post("/api/vocab-quiz-attempts", json=ATTEMPT).status_code == 200
    assert client.post("/api/audio-records", json=AUDIO).status_code == 200

    overview = client.get(f"/api/students/{student['id']}/overview")
    assert overview.status_code == 200
    body = overview.json()

    sub = next(s for s in body["submissions"] if s["id"] == "ov-sub-1")
    assert sub["storyId"] == "story-ov-1"
    # Heavy JSONB is dropped — the page never reads scenes here.
    assert sub["scenes"] == []

    attempt = next(a for a in body["quizAttempts"] if a["id"] == "ov-attempt-1")
    assert attempt["correctCount"] == 15
    assert attempt["totalQuestions"] == 20
    assert attempt["mode"] == "tier1"
    assert attempt["questionResults"] == []

    rec = next(r for r in body["audioRecords"] if r["id"] == "ov-rec-1")
    # Audio keeps praat metrics — the page averages tone/fluency off them.
    assert rec["praatMetrics"] == {"tone_accuracy": 0.82, "fluency_score": 0.7}


def test_overview_is_scoped_to_the_owning_student():
    with contextlib.ExitStack() as stack:
        client_a, student_a = login_new_client(stack, "Student A", "student")
        client_b, student_b = login_new_client(stack, "Student B", "student")
        # A cannot read B's overview.
        assert client_a.get(f"/api/students/{student_b['id']}/overview").status_code == 403
        # A can read their own.
        assert client_a.get(f"/api/students/{student_a['id']}/overview").status_code == 200


def test_teacher_can_read_a_students_overview(logged_in_teacher):
    with contextlib.ExitStack() as stack:
        _, student = login_new_client(stack, "Watched Student", "student")
        teacher_client, _ = logged_in_teacher
        assert teacher_client.get(f"/api/students/{student['id']}/overview").status_code == 200
