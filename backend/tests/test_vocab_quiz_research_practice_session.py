"""POST /api/research/vocabulary/practice-session - auth gating, the 409 for
a non-participant, and that the response never leaks study_id/condition."""
import db
from repositories import research as repo


def _insert_study(study_id: str, status: str, practice_budget: int = 4) -> None:
    with db.connect_db() as conn:
        repo.insert_study(
            conn, id=study_id, name="Test study", status=status,
            config_json={"practiceBudget": practice_budget},
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
            lesson_id="lesson-5", section_id=None, bkt_policy="mastery_blind", retention_policy="yoked",
            sequence_id="A", related_set_id=None, yoke_source_word_id=None,
            assignment_version="v1", created_at="2026-01-01T00:00:00Z",
        )


def test_requires_authentication(anonymous_client):
    response = anonymous_client.post("/api/research/vocabulary/practice-session")
    assert response.status_code in (401, 403)


def test_teacher_is_forbidden(logged_in_teacher):
    client, _ = logged_in_teacher
    response = client.post("/api/research/vocabulary/practice-session")
    assert response.status_code == 403


def test_a_non_participant_gets_409_not_an_empty_session(logged_in_student):
    client, _ = logged_in_student
    response = client.post("/api/research/vocabulary/practice-session")
    assert response.status_code == 409


def test_an_active_participant_gets_their_assigned_words_and_nothing_leaks(logged_in_student):
    client, student = logged_in_student
    _insert_study("study-practice-post", "active", practice_budget=1)
    _insert_participant("study-practice-post", student["id"])
    _assign_word("study-practice-post", student["id"], "word-only")

    response = client.post("/api/research/vocabulary/practice-session")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"wordIds"}
    assert body["wordIds"] == ["word-only"]
    assert "study-practice-post" not in response.text
