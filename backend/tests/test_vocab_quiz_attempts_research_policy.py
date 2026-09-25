"""Epic 3, Task 3.4: POST /api/vocab-quiz-attempts stamps the real,
server-resolved progression policy - never trusts the client for it."""
import db
from repositories import research as repo


def _attempt(attempt_id: str, story_id: str = "story-1") -> dict:
    return {
        "id": attempt_id,
        "storyId": story_id,
        "studentName": "Test Student",
        "mode": "tier1",
        "completedAt": "2026-09-16T00:00:00Z",
        "totalQuestions": 1,
        "correctCount": 1,
        "totalTimeMs": 900,
        "questionResults": [{"word": "學習", "correct": True, "timeMs": 900}],
    }


def test_a_default_student_gets_production_accuracy_stamped(logged_in_student):
    client, student = logged_in_student
    response = client.post("/api/vocab-quiz-attempts", json=_attempt("attempt-default"))
    assert response.status_code == 200
    body = response.json()
    assert body["progressionPolicy"] == "production_accuracy"
    assert body["roundCompleted"] is True
    assert body["researchStudyId"] is None


def test_the_client_cannot_override_the_stamped_policy(logged_in_student):
    client, student = logged_in_student
    payload = _attempt("attempt-spoofed")
    payload["progressionPolicy"] = "research_coverage"  # ignored - not a real field on the request model
    response = client.post("/api/vocab-quiz-attempts", json=payload)
    assert response.status_code == 200
    assert response.json()["progressionPolicy"] == "production_accuracy"


def test_an_active_research_participant_gets_research_coverage_stamped(logged_in_student):
    client, student = logged_in_student
    with db.connect_db() as conn:
        repo.insert_study(
            conn, id="study-attempts", name="Test study", status="active", config_json={},
            policy_version="v1", assignment_version="v1", created_at="2026-01-01T00:00:00Z",
        )
        repo.insert_participant(
            conn, study_id="study-attempts", student_id=student["id"], class_id=None,
            sequence_id=None, active=True, created_at="2026-01-01T00:00:00Z",
        )

    response = client.post("/api/vocab-quiz-attempts", json=_attempt("attempt-research"))
    assert response.status_code == 200
    body = response.json()
    assert body["progressionPolicy"] == "research_coverage"
    assert body["researchStudyId"] == "study-attempts"


def test_listing_attempts_includes_the_stamped_policy(logged_in_student):
    client, student = logged_in_student
    client.post("/api/vocab-quiz-attempts", json=_attempt("attempt-list"))
    response = client.get("/api/vocab-quiz-attempts", params={"story_id": "story-1"})
    assert response.status_code == 200
    attempts = response.json()
    assert attempts[0]["progressionPolicy"] == "production_accuracy"
