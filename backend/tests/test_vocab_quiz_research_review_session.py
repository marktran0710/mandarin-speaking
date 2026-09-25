"""GET /api/research/vocabulary/review-session - auth gating, the 409 for a
non-participant, and that the response never leaks study_id/condition."""
import db
from application.research.retention import enroll_section_retention
from repositories import research as repo


def _insert_study(study_id: str, status: str = "active") -> None:
    with db.connect_db() as conn:
        repo.insert_study(
            conn, id=study_id, name="Test study", status=status, config_json={},
            policy_version="v1", assignment_version="v1", created_at="2026-01-01T00:00:00Z",
        )


def _insert_participant(study_id: str, student_id: str) -> None:
    with db.connect_db() as conn:
        repo.insert_participant(
            conn, study_id=study_id, student_id=student_id, class_id=None,
            sequence_id="A", active=True, created_at="2026-01-01T00:00:00Z",
        )


def _assign_word(study_id: str, student_id: str, word_id: str) -> None:
    with db.connect_db() as conn:
        repo.insert_assignment(
            conn, study_id=study_id, student_id=student_id, word_id=word_id,
            lesson_id="5", section_id="s", bkt_policy="mastery_blind", retention_policy="adaptive_sm2",
            sequence_id="A", related_set_id=None, yoke_source_word_id=None,
            assignment_version="v1", created_at="2026-01-01T00:00:00Z",
        )


def test_requires_authentication(anonymous_client):
    response = anonymous_client.get("/api/research/vocabulary/review-session")
    assert response.status_code in (401, 403)


def test_teacher_is_forbidden(logged_in_teacher):
    client, _ = logged_in_teacher
    response = client.get("/api/research/vocabulary/review-session")
    assert response.status_code == 403


def test_a_non_participant_gets_409(logged_in_student):
    client, _ = logged_in_student
    response = client.get("/api/research/vocabulary/review-session")
    assert response.status_code == 409


def test_an_active_participant_with_a_due_word_gets_it_and_nothing_leaks(logged_in_student):
    client, student = logged_in_student
    _insert_study("study-review-session")
    _insert_participant("study-review-session", student["id"])
    _assign_word("study-review-session", student["id"], "word-due")

    with db.connect_db() as conn:
        from datetime import datetime, timedelta, timezone
        enroll_section_retention(conn, student["id"], "study-review-session", "s", now=datetime.now(timezone.utc) - timedelta(days=30))

    response = client.get("/api/research/vocabulary/review-session")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"wordIds"}
    assert body["wordIds"] == ["word-due"]
    assert "study-review-session" not in response.text
