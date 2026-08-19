"""speaking_progress round-tripping — resumable per-scene speaking practice
state (attempts/bestTone/bestFluency/mastery+content gates/cleared words)."""

PROGRESS = {
    "studentId": "ignored-overwritten-by-identity",
    "topicId": "teacher-story-1",
    "sceneIndex": 0,
    "attempts": 2,
    "bestTone": 78.5,
    "bestFluency": 60.0,
    "masteryPassed": False,
    "contentPassed": True,
    "clearedWords": ["妳", "週末"],
}


def test_speaking_progress_round_trips(logged_in_student):
    client, student = logged_in_student
    assert client.put("/api/speaking-progress", json=PROGRESS).status_code == 200

    rows = client.get(
        "/api/speaking-progress", params={"topic_id": "teacher-story-1"}
    ).json()
    assert len(rows) == 1
    assert rows[0]["studentId"] == student["id"]
    assert rows[0]["sceneIndex"] == 0
    assert rows[0]["attempts"] == 2
    assert rows[0]["bestTone"] == 78.5
    assert rows[0]["contentPassed"] is True
    assert rows[0]["clearedWords"] == ["妳", "週末"]


def test_speaking_progress_upsert_updates_in_place(logged_in_student):
    client, _ = logged_in_student
    client.put("/api/speaking-progress", json=PROGRESS)
    client.put(
        "/api/speaking-progress",
        json={**PROGRESS, "attempts": 3, "masteryPassed": True, "clearedWords": []},
    )

    rows = client.get(
        "/api/speaking-progress", params={"topic_id": "teacher-story-1"}
    ).json()
    assert len(rows) == 1
    assert rows[0]["attempts"] == 3
    assert rows[0]["masteryPassed"] is True
    assert rows[0]["clearedWords"] == []


def test_speaking_progress_scoped_by_scene_index(logged_in_student):
    client, _ = logged_in_student
    client.put("/api/speaking-progress", json=PROGRESS)
    client.put("/api/speaking-progress", json={**PROGRESS, "sceneIndex": 1, "attempts": 1})

    rows = client.get(
        "/api/speaking-progress", params={"topic_id": "teacher-story-1"}
    ).json()
    assert {r["sceneIndex"] for r in rows} == {0, 1}


def test_speaking_progress_scoped_by_student_and_topic(logged_in_student):
    client, student = logged_in_student
    client.put("/api/speaking-progress", json=PROGRESS)
    client.put(
        "/api/speaking-progress",
        json={**PROGRESS, "topicId": "another-story"},
    )

    rows = client.get(
        "/api/speaking-progress", params={"topic_id": "teacher-story-1"}
    ).json()
    assert len(rows) == 1
    assert rows[0]["studentId"] == student["id"]
    assert rows[0]["topicId"] == "teacher-story-1"


def test_speaking_progress_cannot_be_written_for_another_student(logged_in_student):
    """A student can never overwrite another student's row, even if they
    put a different studentId in the request body - the server always
    uses the caller's own verified identity."""
    client, student = logged_in_student
    client.put("/api/speaking-progress", json={**PROGRESS, "studentId": "someone-else"})

    rows = client.get(
        "/api/speaking-progress", params={"topic_id": "teacher-story-1"}
    ).json()
    assert len(rows) == 1
    assert rows[0]["studentId"] == student["id"]


def test_speaking_progress_requires_login(client):
    response = client.get(
        "/api/speaking-progress", params={"topic_id": "teacher-story-1"}
    )
    assert response.status_code == 401


def test_speaking_progress_round_trips_latest_result(logged_in_student):
    client, _ = logged_in_student
    latest_result = {
        "sceneIndex": 0,
        "imageUrl": "/uploads/images/a.png",
        "transcription": "A saved scene",
        "vocabUsed": ["market"],
        "vocabMissing": [],
        "vocabScore": 100,
        "toneAccuracy": 82,
        "pronScore": 76,
        "fluencyScore": 70,
        "audioUrl": "/uploads/audio.wav",
        "selfEvalContent": "good",
        "selfEvalPronunciation": "ok",
    }
    assert client.put(
        "/api/speaking-progress", json={**PROGRESS, "latestResult": latest_result}
    ).status_code == 200

    rows = client.get(
        "/api/speaking-progress", params={"topic_id": "teacher-story-1"}
    ).json()
    assert rows[0]["latestResult"] == latest_result
