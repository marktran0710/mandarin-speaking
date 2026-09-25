"""Admin read model for the synthetic placement workbook import."""

from datetime import datetime, timezone

import db
from analytics.learner_model.bkt.mastery import upsert_raw_responses


def _response(student_id: str, order: int, *, tier: str, correct: bool) -> dict:
    now = "2026-09-25T07:46:01+00:00"
    return {
        "student_id": student_id,
        "word_id": f"WORD-{order}",
        "word": f"Word {order}",
        "lesson_id": "custom-story-1",
        "quiz_id": "PLACEMENT-SIM001-V1",
        "attempt_id": "PLACEMENT-SIM001-V1",
        "item_id": f"Q{order:04d}",
        "question_type": "basic_meaning_mcq" if tier == "tier1" else "context_cloze_mcq",
        "selected_answer": "correct" if correct else "wrong",
        "correct_answer": "correct",
        "presented_options": [],
        "question_prompt": "Choose an answer.",
        "answered_at": now,
        "bkt_eligible": True,
        "diagnostic_exposure_id": f"placement:PLACEMENT-SIM001-V1:Q{order:04d}",
        "bkt_eligibility_errors": [],
        "correct": correct,
        "response_time_ms": 1000,
        "occurred_at": now,
        "occurred_at_utc": datetime(2026, 9, 25, 7, 46, 1, tzinfo=timezone.utc),
        "evidence_origin": "synthetic",
        "resolver_version": "placement-workbook-import-v1",
        "attempt_order": order - 1,
        "quiz_level": tier,
        "quiz_mode": tier,
        "round_type": "1" if tier == "tier1" else "3",
        "knowledge_dimension": "meaning" if tier == "tier1" else "contextual_recall",
        "activity_type": "diagnostic",
        "research_study_id": None,
    }


def _seed_import_batch() -> None:
    with db.connect_db() as connection:
        connection.execute(
            """
            INSERT INTO students
                (id, name, password, password_reset_required, status, is_test_account)
            VALUES ('SIM001', 'Synthetic Student 001', 'hash', TRUE, 'active', TRUE)
            """
        )
        connection.execute(
            """
            INSERT INTO placement_test_attempts
                (id, student_id, blueprint_revision, question_snapshot, response_snapshot,
                 status, started_at, completed_at, total_questions, correct_count,
                 total_time_ms, created_at, updated_at)
            VALUES ('PLACEMENT-SIM001-V1', 'SIM001', 1, '[]'::jsonb, '[]'::jsonb,
                    'completed', '2026-09-25T07:46:01+00:00', '2026-09-25T07:46:01+00:00',
                    2, 1, 2000, '2026-09-25T07:46:01+00:00', '2026-09-25T07:46:01+00:00')
            """
        )
        upsert_raw_responses(
            connection,
            [_response("SIM001", 1, tier="tier1", correct=True), _response("SIM001", 2, tier="tier3", correct=False)],
        )
        connection.execute(
            """
            INSERT INTO student_vocab_mastery
                (student_id, word_id, p_learned, observation_count, correct_count,
                 incorrect_count, last_response_at, last_item_id, last_question_type,
                 last_lesson_id, model_version, parameter_fingerprint, created_at, updated_at)
            VALUES
                ('SIM001', 'WORD-1', .6, 1, 1, 0, '2026-09-25T07:46:01+00:00', 'Q0001',
                 'basic_meaning_mcq', 'custom-story-1', 'format-aware-bkt-v2', 'fingerprint',
                 '2026-09-25T07:46:01+00:00', '2026-09-25T07:46:01+00:00'),
                ('SIM001', 'WORD-2', .17, 1, 0, 1, '2026-09-25T07:46:01+00:00', 'Q0002',
                 'context_cloze_mcq', 'custom-story-1', 'format-aware-bkt-v2', 'fingerprint',
                 '2026-09-25T07:46:01+00:00', '2026-09-25T07:46:01+00:00')
            """
        )


def test_admin_placement_data_requires_admin(anonymous_client):
    response = anonymous_client.get("/api/admin/placement-test/results")
    assert response.status_code in (401, 403)


def test_admin_placement_data_summarizes_imported_batch(admin_client):
    _seed_import_batch()

    response = admin_client.get("/api/admin/placement-test/results")

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["summary"] == {
        "studentCount": 1,
        "attemptCount": 1,
        "responseCount": 2,
        "correctCount": 1,
        "incorrectCount": 1,
        "accuracy": 50.0,
        "tier1": {"responseCount": 1, "correctCount": 1, "incorrectCount": 0, "accuracy": 100.0},
        "tier3": {"responseCount": 1, "correctCount": 0, "incorrectCount": 1, "accuracy": 0.0},
        "masteryRowCount": 2,
        "masteryStatuses": {"UNASSESSED": 2},
    }
    assert body["students"][0]["studentId"] == "SIM001"
    assert body["students"][0]["responses"][1]["status"] == "UNASSESSED"
