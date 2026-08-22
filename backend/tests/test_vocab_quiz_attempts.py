"""Tests for the vocab quiz attempt tracking endpoints."""
import contextlib

from conftest import login_new_client


def test_create_and_list_vocab_quiz_attempt(logged_in_student):
    client, student = logged_in_student
    attempt = {
        "id": "test-attempt-1",
        "storyId": "test-story-1",
        "studentName": "Test Student",
        "baseStoryId": "test-story-1",
        "level": "medium",
        "completedAt": "2026-07-08T00:00:00.000Z",
        "totalQuestions": 3,
        "correctCount": 2,
        "totalTimeMs": 15000,
        "questionResults": [
            {
                "word": "餐廳",
                "correct": True,
                "timeMs": 4000,
                "itemId": "test-story-1:%E9%A4%90%E5%BB%B3:translation:v1",
                "conceptId": "餐廳",
                "questionKind": "translation",
                "level": "medium",
                "baseStoryId": "test-story-1",
                "itemVersion": "v1",
            },
            {"word": "吃", "correct": True, "timeMs": 5000},
            {"word": "喝", "correct": False, "timeMs": 6000},
        ],
    }

    post_response = client.post("/api/vocab-quiz-attempts", json=attempt)
    assert post_response.status_code == 200
    body = post_response.json()
    assert body["studentId"] == student["id"]
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
    assert attempts[0]["baseStoryId"] == "test-story-1"
    assert attempts[0]["level"] == "medium"


def test_list_is_scoped_to_the_logged_in_student(logged_in_student):
    client, student = logged_in_student
    base = {
        "storyId": "test-story-2",
        "completedAt": "2026-07-08T00:00:00.000Z",
        "totalQuestions": 1,
        "correctCount": 1,
        "totalTimeMs": 1000,
        "questionResults": [{"word": "水", "correct": True, "timeMs": 1000}],
    }
    client.post("/api/vocab-quiz-attempts", json={**base, "id": "attempt-a", "studentName": "Alice"})

    with contextlib.ExitStack() as stack:
        bob_client, _ = login_new_client(stack, "Bob", "student")
        bob_client.post(
            "/api/vocab-quiz-attempts",
            json={**base, "id": "attempt-b", "studentName": "Bob"},
        )

    response = client.get(
        "/api/vocab-quiz-attempts", params={"story_id": "test-story-2"}
    )
    attempts = response.json()
    assert len(attempts) == 1
    assert attempts[0]["studentName"] == "Alice"
    assert attempts[0]["studentId"] == student["id"]


def test_mode_round_trips(logged_in_student):
    client, _ = logged_in_student
    attempt = {
        "id": "test-attempt-mode",
        "storyId": "test-story-mode",
        "studentName": "Test Student",
        "mode": "speed",
        "completedAt": "2026-07-08T00:00:00.000Z",
        "totalQuestions": 1,
        "correctCount": 1,
        "totalTimeMs": 1000,
        "questionResults": [{"word": "水", "correct": True, "timeMs": 1000}],
    }

    post_response = client.post("/api/vocab-quiz-attempts", json=attempt)
    assert post_response.status_code == 200
    assert post_response.json()["mode"] == "speed"

    list_response = client.get(
        "/api/vocab-quiz-attempts", params={"story_id": "test-story-mode"}
    )
    assert list_response.json()[0]["mode"] == "speed"


def test_mode_is_null_when_not_provided(logged_in_student):
    client, _ = logged_in_student
    attempt = {
        "id": "test-attempt-no-mode",
        "storyId": "test-story-no-mode",
        "studentName": "Test Student",
        "completedAt": "2026-07-08T00:00:00.000Z",
        "totalQuestions": 1,
        "correctCount": 1,
        "totalTimeMs": 1000,
        "questionResults": [{"word": "水", "correct": True, "timeMs": 1000}],
    }

    post_response = client.post("/api/vocab-quiz-attempts", json=attempt)
    assert post_response.status_code == 200
    assert post_response.json()["mode"] is None


def test_weak_words_requires_login(client):
    response = client.get("/api/vocab-quiz-attempts/weak-words", params={"story_id": "s"})
    assert response.status_code == 401


def test_weak_words_returns_only_words_wrong_in_their_most_recent_attempt(logged_in_student):
    client, _ = logged_in_student
    # First attempt: both words wrong.
    client.post(
        "/api/vocab-quiz-attempts",
        json={
            "id": "weak-attempt-1",
            "storyId": "weak-story",
            "studentName": "Alice",
            "completedAt": "2026-07-08T00:00:00.000Z",
            "totalQuestions": 2,
            "correctCount": 0,
            "totalTimeMs": 2000,
            "questionResults": [
                {"word": "餐廳", "correct": False, "timeMs": 1000},
                {"word": "吃", "correct": False, "timeMs": 1000},
            ],
        },
    )
    # Second, later attempt: got 餐廳 right this time, 吃 still wrong.
    client.post(
        "/api/vocab-quiz-attempts",
        json={
            "id": "weak-attempt-2",
            "storyId": "weak-story",
            "studentName": "Alice",
            "completedAt": "2026-07-09T00:00:00.000Z",
            "totalQuestions": 2,
            "correctCount": 1,
            "totalTimeMs": 2000,
            "questionResults": [
                {"word": "餐廳", "correct": True, "timeMs": 1000},
                {"word": "吃", "correct": False, "timeMs": 1000},
            ],
        },
    )

    response = client.get(
        "/api/vocab-quiz-attempts/weak-words",
        params={"story_id": "weak-story"},
    )
    assert response.status_code == 200
    assert response.json()["words"] == ["吃"]


def test_weak_words_is_scoped_to_the_logged_in_student(logged_in_student):
    client, _ = logged_in_student
    with contextlib.ExitStack() as stack:
        bob_client, _ = login_new_client(stack, "Bob", "student")
        bob_client.post(
            "/api/vocab-quiz-attempts",
            json={
                "id": "weak-attempt-other-student",
                "storyId": "weak-story-2",
                "studentName": "Bob",
                "completedAt": "2026-07-08T00:00:00.000Z",
                "totalQuestions": 1,
                "correctCount": 0,
                "totalTimeMs": 1000,
                "questionResults": [{"word": "水", "correct": False, "timeMs": 1000}],
            },
        )

    response = client.get(
        "/api/vocab-quiz-attempts/weak-words",
        params={"story_id": "weak-story-2"},
    )
    assert response.status_code == 200
    assert response.json()["words"] == []


def test_rejects_attempt_with_no_questions(logged_in_student):
    client, _ = logged_in_student
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
