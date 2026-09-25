"""GET /api/research/vocabulary/admin/summary (Epic 8, Task 8.3/8.4) - admin
only, and its response shape/values."""
import db
from application.research.logging import record_policy_event
from repositories import research as repo


def _insert_study(study_id: str, status: str = "active") -> None:
    with db.connect_db() as conn:
        repo.insert_study(
            conn, id=study_id, name="Test study", status=status, config_json={},
            policy_version="v1", assignment_version="v1", created_at="2026-01-01T00:00:00Z",
        )


def _insert_participant(study_id: str, student_id: str, active: bool = True) -> None:
    with db.connect_db() as conn:
        repo.insert_participant(
            conn, study_id=study_id, student_id=student_id, class_id=None,
            sequence_id="A", active=active, created_at="2026-01-01T00:00:00Z",
        )


def _assign(study_id: str, student_id: str, word_id: str, *, bkt_policy: str, retention_policy: str) -> None:
    with db.connect_db() as conn:
        repo.insert_assignment(
            conn, study_id=study_id, student_id=student_id, word_id=word_id,
            lesson_id="5", section_id="s", bkt_policy=bkt_policy, retention_policy=retention_policy,
            sequence_id="A", related_set_id=None, yoke_source_word_id=None,
            assignment_version="v1", created_at="2026-01-01T00:00:00Z",
        )


def test_requires_authentication(anonymous_client):
    response = anonymous_client.get("/api/research/vocabulary/admin/summary?study_id=study-1")
    assert response.status_code in (401, 403)


def test_a_student_is_forbidden(logged_in_student):
    client, _ = logged_in_student
    response = client.get("/api/research/vocabulary/admin/summary?study_id=study-1")
    assert response.status_code == 403


def test_a_teacher_is_forbidden(logged_in_teacher):
    client, _ = logged_in_teacher
    response = client.get("/api/research/vocabulary/admin/summary?study_id=study-1")
    assert response.status_code == 403


def test_an_unknown_study_is_404(admin_client):
    response = admin_client.get("/api/research/vocabulary/admin/summary?study_id=no-such-study")
    assert response.status_code == 404


def test_an_admin_sees_the_full_summary_shape(admin_client):
    study_id = "study-admin-http"
    _insert_study(study_id)
    _insert_participant(study_id, "student-1")
    _assign(study_id, "student-1", "word-a", bkt_policy="mastery_blind", retention_policy="yoked")
    _assign(study_id, "student-1", "word-b", bkt_policy="bkt_personalized", retention_policy="adaptive_sm2")
    with db.connect_db() as conn:
        record_policy_event(conn, study_id=study_id, student_id="student-1", event_type="core_completed", payload={"sectionId": "s"}, occurred_at=None)

    response = admin_client.get(f"/api/research/vocabulary/admin/summary?study_id={study_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["studyId"] == study_id
    assert body["participants"] == {"active": 1, "total": 1}
    assert body["totalAssignments"] == 2
    assert body["assignmentBalance"] == {"C": 1, "BS": 1}
    assert body["fidelity"]["coreCompletedCount"] == 1
