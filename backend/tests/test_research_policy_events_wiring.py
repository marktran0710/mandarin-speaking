"""Epic 8, Task 8.1: proves each Epic 3-7 orchestration function actually
writes the policy event it's supposed to, with the right word/condition
payload - not just that the underlying feature still works (that's already
covered by each feature's own test file)."""
from datetime import datetime, timedelta, timezone

import db
from application.research_practice_session import build_practice_session
from application.research_probes import enroll_section_probes, submit_probe_response
from application.research_retention import apply_retention_review, enroll_section_retention
from repositories import vocabulary_research as repo

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _create_study(study_id: str, config: dict | None = None) -> None:
    with db.connect_db() as conn:
        repo.insert_study(
            conn, id=study_id, name="Test study", status="active", config_json=config or {},
            policy_version="v1", assignment_version="v1", created_at="2026-01-01T00:00:00Z",
        )


def _add_participant(study_id: str, student_id: str) -> None:
    with db.connect_db() as conn:
        repo.insert_participant(
            conn, study_id=study_id, student_id=student_id, class_id=None,
            sequence_id="A", active=True, created_at="2026-01-01T00:00:00Z",
        )


def _assign(study_id, student_id, word_id, *, section_id="s", bkt_policy="mastery_blind", retention_policy="adaptive_sm2", yoke_source_word_id=None):
    with db.connect_db() as conn:
        repo.insert_assignment(
            conn, study_id=study_id, student_id=student_id, word_id=word_id,
            lesson_id="5", section_id=section_id, bkt_policy=bkt_policy, retention_policy=retention_policy,
            sequence_id="A", related_set_id=None, yoke_source_word_id=yoke_source_word_id,
            assignment_version="v1", created_at="2026-01-01T00:00:00Z",
        )


def _insert_item(study_id: str, word_id: str, assessment_type: str, *, correct_answer="A") -> str:
    item_id = f"item-{study_id}-{word_id}-{assessment_type}"
    with db.connect_db() as conn:
        repo.insert_assessment_item(
            conn, id=item_id, study_id=study_id, word_id=word_id, assessment_type=assessment_type,
            question_type="mc_translation", prompt="prompt", choices=["A", "B"],
            correct_answer=correct_answer, created_at="2026-01-01T00:00:00Z",
        )
    return item_id


def _events(study_id: str, event_type: str) -> list[dict]:
    with db.connect_db() as conn:
        return conn.execute(
            "SELECT * FROM vocab_research_policy_events WHERE study_id = %s AND event_type = %s ORDER BY id",
            (study_id, event_type),
        ).fetchall()


class TestPracticeSessionEvents:
    def test_logs_a_session_created_event_and_one_item_selected_event_per_word_with_condition(self):
        study_id = "study-events-practice"
        _create_study(study_id, config={"practiceBudget": 2})
        _add_participant(study_id, "student-1")
        _assign(study_id, "student-1", "word-c", bkt_policy="mastery_blind", retention_policy="yoked")
        _assign(study_id, "student-1", "word-b", bkt_policy="bkt_personalized", retention_policy="yoked")

        with db.connect_db() as conn:
            build_practice_session(conn, "student-1")

        created = _events(study_id, "practice_session_created")
        selected = _events(study_id, "practice_item_selected")
        assert len(created) == 1
        assert len(selected) == 2
        conditions = {event["word_id"]: event["payload_json"]["condition"] for event in selected}
        assert conditions == {"word-c": "C", "word-b": "B"}


class TestRetentionEvents:
    def test_logs_a_retention_enrolled_event_per_word_with_condition(self):
        study_id = "study-events-retention-enroll"
        _create_study(study_id)
        _assign(study_id, "student-1", "word-a", bkt_policy="mastery_blind", retention_policy="adaptive_sm2")

        with db.connect_db() as conn:
            enroll_section_retention(conn, "student-1", study_id, "s", now=NOW)

        events = _events(study_id, "retention_enrolled")
        assert len(events) == 1
        assert events[0]["word_id"] == "word-a"
        assert events[0]["payload_json"]["condition"] == "S"

    def test_logs_review_scheduled_for_a_graded_adaptive_word_and_review_yoked_for_its_mirror(self):
        study_id = "study-events-review"
        _create_study(study_id)
        _assign(study_id, "student-1", "word-source", bkt_policy="bkt_personalized", retention_policy="adaptive_sm2")
        _assign(study_id, "student-1", "word-yoked", bkt_policy="bkt_personalized", retention_policy="yoked", yoke_source_word_id="word-source")

        with db.connect_db() as conn:
            enroll_section_retention(conn, "student-1", study_id, "s", now=NOW)
            due_time = NOW + timedelta(days=1, hours=1)
            apply_retention_review(
                conn, "student-1", study_id,
                [{"conceptId": "word-source", "correct": True, "authoritativeResolved": True, "activityType": "scheduled_maintenance", "quizId": "q1", "sourceResponseId": "q1:0"}],
                now=due_time,
            )

        scheduled = _events(study_id, "review_scheduled")
        yoked = _events(study_id, "review_yoked")
        assert len(scheduled) == 1
        assert scheduled[0]["word_id"] == "word-source"
        assert scheduled[0]["payload_json"]["condition"] == "BS"
        assert len(yoked) == 1
        assert yoked[0]["word_id"] == "word-yoked"
        assert yoked[0]["payload_json"]["condition"] == "B"
        assert yoked[0]["payload_json"]["sourceWordId"] == "word-source"

    def test_logs_review_completed_via_the_response_routing_orchestrator(self):
        from application.vocabulary_research import apply_response_routing
        from domain.vocabulary.research_policy import build_research_context
        from types import SimpleNamespace

        study_id = "study-events-review-completed"
        _create_study(study_id)
        _assign(study_id, "student-1", "word-a", bkt_policy="mastery_blind", retention_policy="adaptive_sm2")
        context = build_research_context(
            study_id=study_id, study_status="active", policy_version="v1", assignment_version="v1",
            practice_budget=None, participant_active=True,
        )
        with db.connect_db() as conn:
            enroll_section_retention(conn, "student-1", study_id, "s", now=NOW)
            due_time = NOW + timedelta(days=1, hours=1)
            attempt = SimpleNamespace(id="attempt-1", mode="maintenance_review")
            apply_response_routing(
                conn, "student-1", context, attempt,
                [{"conceptId": "word-a", "correct": True, "authoritativeResolved": True, "activityType": "scheduled_maintenance", "quizId": "q1"}],
                now_override=due_time,
            )
        events = _events(study_id, "review_completed")
        assert len(events) == 1
        assert events[0]["payload_json"]["wordsUpdated"] == 1


class TestProbeEvents:
    def test_logs_a_probe_assigned_event_with_condition(self):
        study_id = "study-events-probe-assign"
        _create_study(study_id)
        _assign(study_id, "student-1", "word-a", bkt_policy="bkt_personalized", retention_policy="adaptive_sm2")
        for probe_type in ("probe_7d", "probe_21d", "final_retention"):
            _insert_item(study_id, "word-a", probe_type)

        with db.connect_db() as conn:
            enroll_section_probes(conn, "student-1", study_id, "s", now=NOW)

        events = _events(study_id, "probe_assigned")
        assert len(events) == 1
        assert events[0]["word_id"] == "word-a"
        assert events[0]["payload_json"]["condition"] == "BS"

    def test_logs_a_probe_completed_event_with_the_grading_outcome(self):
        study_id = "study-events-probe-complete"
        _create_study(study_id)
        item_id = _insert_item(study_id, "word-a", "probe_7d", correct_answer="B")
        with db.connect_db() as conn:
            repo.insert_probe_assignment(
                conn, study_id=study_id, student_id="student-1", word_id="word-a",
                assessment_item_id=item_id, probe_type="probe_7d",
                due_at=NOW - timedelta(days=1), assigned_at=NOW, created_at=NOW.isoformat(),
            )
            assignment_id = repo.find_probe_assignments_for_student(conn, study_id, "student-1")["word-a"]["id"]
            submit_probe_response(conn, "student-1", assignment_id, "B", source_response_id="src-1", now=NOW)

        events = _events(study_id, "probe_completed")
        assert len(events) == 1
        assert events[0]["word_id"] == "word-a"
        assert events[0]["payload_json"]["correct"] is True
