"""Tests for the vocab quiz attempt tracking endpoints."""


def test_create_and_list_vocab_quiz_attempt(client):
    attempt = {
        "id": "test-attempt-1",
        "storyId": "test-story-1",
        "studentName": "Test Student",
        "completedAt": "2026-07-08T00:00:00.000Z",
        "totalQuestions": 3,
        "correctCount": 2,
        "totalTimeMs": 15000,
        "questionResults": [
            {"word": "餐廳", "correct": True, "timeMs": 4000},
            {"word": "吃", "correct": True, "timeMs": 5000},
            {"word": "喝", "correct": False, "timeMs": 6000},
        ],
    }

    post_response = client.post("/api/vocab-quiz-attempts", json=attempt)
    assert post_response.status_code == 200
    body = post_response.json()
    assert body["correctCount"] == 2
    assert body["totalQuestions"] == 3

    list_response = client.get(
        "/api/vocab-quiz-attempts", params={"story_id": "test-story-1"}
    )
    assert list_response.status_code == 200
    attempts = list_response.json()
    assert len(attempts) == 1
    assert attempts[0]["id"] == "test-attempt-1"
    assert attempts[0]["studentName"] == "Test Student"
    assert attempts[0]["totalTimeMs"] == 15000
    assert attempts[0]["questionResults"] == attempt["questionResults"]


def test_list_filters_by_student_name(client):
    base = {
        "storyId": "test-story-2",
        "completedAt": "2026-07-08T00:00:00.000Z",
        "totalQuestions": 1,
        "correctCount": 1,
        "totalTimeMs": 1000,
        "questionResults": [{"word": "水", "correct": True, "timeMs": 1000}],
    }
    client.post("/api/vocab-quiz-attempts", json={**base, "id": "attempt-a", "studentName": "Alice"})
    client.post("/api/vocab-quiz-attempts", json={**base, "id": "attempt-b", "studentName": "Bob"})

    response = client.get(
        "/api/vocab-quiz-attempts",
        params={"story_id": "test-story-2", "student_name": "Alice"},
    )
    attempts = response.json()
    assert len(attempts) == 1
    assert attempts[0]["studentName"] == "Alice"


def test_rejects_attempt_with_no_questions(client):
    attempt = {
        "id": "test-attempt-invalid",
        "storyId": "test-story-3",
        "studentName": "Test Student",
        "completedAt": "2026-07-08T00:00:00.000Z",
        "totalQuestions": 0,
        "correctCount": 0,
        "totalTimeMs": 0,
        "questionResults": [],
    }
    response = client.post("/api/vocab-quiz-attempts", json=attempt)
    assert response.status_code == 422
