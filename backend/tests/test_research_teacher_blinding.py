"""Epic 8, Task 8.5: the normal Teacher Dashboard must never leak
experimental condition/algorithm labels, even for a student who is an
active research participant with real assignment/event data. The teacher
still sees participation, lesson progress, and quiz attempts - just never
C/BKT/SRS/BS or the underlying policy vocabulary."""
import db
from application.research.logging import record_policy_event
from repositories import research as repo

# Task 10.4's own forbidden list, checked here at the teacher-facing surface
# rather than waiting for that later Epic's UI sweep.
_FORBIDDEN_SUBSTRINGS = (
    "bkt_personalized",
    "mastery_blind",
    "adaptive_sm2",
    "P(Learned)",
    "p_learned",
    "AssignmentCondition",
)


def _seed_research_participant(study_id: str, student_id: str) -> None:
    with db.connect_db() as conn:
        repo.insert_study(
            conn, id=study_id, name="Secret condition study", status="active", config_json={},
            policy_version="v1", assignment_version="v1", created_at="2026-01-01T00:00:00Z",
        )
        repo.insert_participant(
            conn, study_id=study_id, student_id=student_id, class_id=None,
            sequence_id="A", active=True, created_at="2026-01-01T00:00:00Z",
        )
        repo.insert_assignment(
            conn, study_id=study_id, student_id=student_id, word_id="word-a",
            lesson_id="5", section_id="s", bkt_policy="bkt_personalized", retention_policy="adaptive_sm2",
            sequence_id="A", related_set_id=None, yoke_source_word_id=None,
            assignment_version="v1", created_at="2026-01-01T00:00:00Z",
        )
        record_policy_event(
            conn, study_id=study_id, student_id=student_id, event_type="practice_item_selected",
            word_id="word-a", payload={"condition": "BS"}, occurred_at=None,
        )


def test_teacher_student_list_never_leaks_condition_vocabulary(logged_in_teacher, logged_in_student):
    client, _ = logged_in_teacher
    _, student = logged_in_student
    _seed_research_participant("study-blind-list", student["id"])

    response = client.get("/api/students")
    assert response.status_code == 200
    for forbidden in _FORBIDDEN_SUBSTRINGS:
        assert forbidden not in response.text


def test_teacher_student_overview_never_leaks_condition_vocabulary(logged_in_teacher, logged_in_student):
    client, _ = logged_in_teacher
    _, student = logged_in_student
    _seed_research_participant("study-blind-overview", student["id"])

    response = client.get(f"/api/students/{student['id']}/overview")
    assert response.status_code == 200
    for forbidden in _FORBIDDEN_SUBSTRINGS:
        assert forbidden not in response.text


def test_teacher_facing_vocab_quiz_attempts_never_leaks_condition_vocabulary(logged_in_teacher, logged_in_student):
    client, _ = logged_in_teacher
    _, student = logged_in_student
    _seed_research_participant("study-blind-attempts", student["id"])

    response = client.get(f"/api/vocab-quiz-attempts?student_id={student['id']}")
    assert response.status_code == 200
    for forbidden in _FORBIDDEN_SUBSTRINGS:
        assert forbidden not in response.text
