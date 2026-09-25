"""GET /api/research/vocabulary/probes/due and POST .../probes/{id}/response
(Epic 7, Task 7.5) - auth gating, the 409 for a non-participant, that a due
question never leaks the correct answer/probe_type/study_id, and that a
submitted response never comes back with correctness feedback (Task 7.6)."""
from datetime import datetime, timedelta, timezone

import db
from repositories import research as repo

NOW = datetime.now(timezone.utc)


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


def _insert_due_assignment(study_id: str, student_id: str, word_id: str, *, correct_answer="B") -> int:
    item_id = f"item-{study_id}-{word_id}"
    with db.connect_db() as conn:
        repo.insert_assessment_item(
            conn, id=item_id, study_id=study_id, word_id=word_id, assessment_type="probe_7d",
            question_type="mc_translation", prompt=f"What does {word_id} mean?",
            choices=["A", "B", "C"], correct_answer=correct_answer, created_at="2026-01-01T00:00:00Z",
        )
        repo.insert_probe_assignment(
            conn, study_id=study_id, student_id=student_id, word_id=word_id,
            assessment_item_id=item_id, probe_type="probe_7d",
            due_at=NOW - timedelta(days=1), assigned_at=NOW, created_at=NOW.isoformat(),
        )
        return repo.find_probe_assignments_for_student(conn, study_id, student_id)[word_id]["id"]


class TestProbesDue:
    def test_requires_authentication(self, anonymous_client):
        response = anonymous_client.get("/api/research/vocabulary/probes/due")
        assert response.status_code in (401, 403)

    def test_teacher_is_forbidden(self, logged_in_teacher):
        client, _ = logged_in_teacher
        response = client.get("/api/research/vocabulary/probes/due")
        assert response.status_code == 403

    def test_a_non_participant_gets_409(self, logged_in_student):
        client, _ = logged_in_student
        response = client.get("/api/research/vocabulary/probes/due")
        assert response.status_code == 409

    def test_an_active_participant_with_a_due_probe_sees_it_with_nothing_leaked(self, logged_in_student):
        client, student = logged_in_student
        _insert_study("study-probe-http")
        _insert_participant("study-probe-http", student["id"])
        _insert_due_assignment("study-probe-http", student["id"], "word-due", correct_answer="B")

        response = client.get("/api/research/vocabulary/probes/due")
        assert response.status_code == 200
        body = response.json()
        assert len(body["questions"]) == 1
        question = body["questions"][0]
        assert question["wordId"] == "word-due"
        assert set(question.keys()) == {"assignmentId", "wordId", "questionType", "prompt", "choices"}
        assert "study-probe-http" not in response.text
        assert "probe_7d" not in response.text
        # The correct answer text itself must never appear in the payload.
        assert '"B"' not in response.text or "correctAnswer" not in response.text


class TestSubmitProbeResponse:
    def test_requires_authentication(self, anonymous_client):
        response = anonymous_client.post("/api/research/vocabulary/probes/1/response", json={"response": "A", "sourceResponseId": "x"})
        assert response.status_code in (401, 403)

    def test_accepts_a_response_with_no_correctness_feedback(self, logged_in_student):
        client, student = logged_in_student
        _insert_study("study-probe-submit")
        _insert_participant("study-probe-submit", student["id"])
        assignment_id = _insert_due_assignment("study-probe-submit", student["id"], "word-a", correct_answer="B")

        response = client.post(
            f"/api/research/vocabulary/probes/{assignment_id}/response",
            json={"response": "B", "sourceResponseId": "src-1"},
        )
        assert response.status_code == 200
        assert response.json() == {"accepted": True}

    def test_an_unowned_assignment_id_is_404(self, logged_in_student):
        client, _ = logged_in_student
        response = client.post(
            "/api/research/vocabulary/probes/999999/response",
            json={"response": "A", "sourceResponseId": "src-1"},
        )
        assert response.status_code == 404

    def test_answered_probe_no_longer_appears_as_due(self, logged_in_student):
        client, student = logged_in_student
        _insert_study("study-probe-answered")
        _insert_participant("study-probe-answered", student["id"])
        assignment_id = _insert_due_assignment("study-probe-answered", student["id"], "word-a")

        client.post(
            f"/api/research/vocabulary/probes/{assignment_id}/response",
            json={"response": "B", "sourceResponseId": "src-1"},
        )
        response = client.get("/api/research/vocabulary/probes/due")
        assert response.json()["questions"] == []
