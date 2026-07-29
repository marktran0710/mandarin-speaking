"""speaking_progress round-tripping — resumable per-scene speaking practice
state (attempts/bestTone/bestFluency/mastery+content gates/cleared words)."""

PROGRESS = {
    "studentId": "student-1",
    "topicId": "teacher-story-1",
    "sceneIndex": 0,
    "attempts": 2,
    "bestTone": 78.5,
    "bestFluency": 60.0,
    "masteryPassed": False,
    "contentPassed": True,
    "clearedWords": ["妳", "週末"],
}


def test_speaking_progress_round_trips(client):
    assert client.put("/api/speaking-progress", json=PROGRESS).status_code == 200

    rows = client.get(
        "/api/speaking-progress",
        params={"student_id": "student-1", "topic_id": "teacher-story-1"},
    ).json()
    assert len(rows) == 1
    assert rows[0]["sceneIndex"] == 0
    assert rows[0]["attempts"] == 2
    assert rows[0]["bestTone"] == 78.5
    assert rows[0]["contentPassed"] is True
    assert rows[0]["clearedWords"] == ["妳", "週末"]


def test_speaking_progress_upsert_updates_in_place(client):
    client.put("/api/speaking-progress", json=PROGRESS)
    client.put(
        "/api/speaking-progress",
        json={**PROGRESS, "attempts": 3, "masteryPassed": True, "clearedWords": []},
    )

    rows = client.get(
        "/api/speaking-progress",
        params={"student_id": "student-1", "topic_id": "teacher-story-1"},
    ).json()
    assert len(rows) == 1
    assert rows[0]["attempts"] == 3
    assert rows[0]["masteryPassed"] is True
    assert rows[0]["clearedWords"] == []


def test_speaking_progress_scoped_by_scene_index(client):
    client.put("/api/speaking-progress", json=PROGRESS)
    client.put("/api/speaking-progress", json={**PROGRESS, "sceneIndex": 1, "attempts": 1})

    rows = client.get(
        "/api/speaking-progress",
        params={"student_id": "student-1", "topic_id": "teacher-story-1"},
    ).json()
    assert {r["sceneIndex"] for r in rows} == {0, 1}


def test_speaking_progress_scoped_by_student_and_topic(client):
    client.put("/api/speaking-progress", json=PROGRESS)
    client.put(
        "/api/speaking-progress",
        json={**PROGRESS, "studentId": "student-2"},
    )
    client.put(
        "/api/speaking-progress",
        json={**PROGRESS, "topicId": "another-story"},
    )

    rows = client.get(
        "/api/speaking-progress",
        params={"student_id": "student-1", "topic_id": "teacher-story-1"},
    ).json()
    assert len(rows) == 1
    assert rows[0]["studentId"] == "student-1"
    assert rows[0]["topicId"] == "teacher-story-1"
