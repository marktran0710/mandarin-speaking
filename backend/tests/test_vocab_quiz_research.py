"""GET /api/research/vocabulary/context - auth gating, safe-field shape,
and that it reflects real vocab_research_participants/studies rows."""
import db
from repositories import vocabulary_research as repo


def _insert_study(study_id: str, status: str, config: dict | None = None) -> None:
    with db.connect_db() as conn:
        repo.insert_study(
            conn,
            id=study_id,
            name="Test study",
            status=status,
            config_json=config or {},
            policy_version="v1",
            assignment_version="v1",
            created_at="2026-01-01T00:00:00Z",
        )


def _insert_participant(study_id: str, student_id: str, active: bool = True) -> None:
    with db.connect_db() as conn:
        repo.insert_participant(
            conn,
            study_id=study_id,
            student_id=student_id,
            class_id=None,
            sequence_id=None,
            active=active,
            created_at="2026-01-01T00:00:00Z",
        )


def test_requires_authentication(anonymous_client):
    response = anonymous_client.get("/api/research/vocabulary/context")
    assert response.status_code in (401, 403)


def test_teacher_is_forbidden(logged_in_teacher):
    client, _ = logged_in_teacher
    response = client.get("/api/research/vocabulary/context")
    assert response.status_code == 403


def test_a_student_with_no_participation_sees_inactive_production_policy(logged_in_student):
    client, _ = logged_in_student
    response = client.get("/api/research/vocabulary/context")
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "active": False,
        "coreCompletionPolicy": "production_accuracy",
        "practiceAvailable": False,
        "reviewAvailable": False,
        "probeAvailable": False,
    }


def test_an_active_participant_sees_research_coverage_policy(logged_in_student):
    client, student = logged_in_student
    _insert_study("study-active", "active", config={"practiceBudget": 8})
    _insert_participant("study-active", student["id"])

    response = client.get("/api/research/vocabulary/context")
    assert response.status_code == 200
    body = response.json()
    assert body["active"] is True
    assert body["coreCompletionPolicy"] == "research_coverage"


def test_response_never_exposes_study_id_or_condition_or_versions(logged_in_student):
    client, student = logged_in_student
    _insert_study("study-secret", "active", config={"practiceBudget": 8})
    _insert_participant("study-secret", student["id"])

    response = client.get("/api/research/vocabulary/context")
    body = response.json()
    assert set(body.keys()) == {
        "active",
        "coreCompletionPolicy",
        "practiceAvailable",
        "reviewAvailable",
        "probeAvailable",
    }
    assert "study-secret" not in response.text
    assert "practiceBudget" not in response.text
    assert "policyVersion" not in response.text
    assert "assignmentVersion" not in response.text


def test_a_draft_study_participant_still_sees_the_default_inactive_response(logged_in_student):
    client, student = logged_in_student
    _insert_study("study-draft", "draft")
    _insert_participant("study-draft", student["id"])

    response = client.get("/api/research/vocabulary/context")
    body = response.json()
    assert body["active"] is False
    assert body["coreCompletionPolicy"] == "production_accuracy"


def test_a_deactivated_participant_sees_production_policy_even_in_an_active_study(logged_in_student):
    client, student = logged_in_student
    _insert_study("study-active-2", "active")
    _insert_participant("study-active-2", student["id"], active=False)

    response = client.get("/api/research/vocabulary/context")
    body = response.json()
    assert body["active"] is False
