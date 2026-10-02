"""Admin read model for the synthetic placement workbook import."""

from datetime import datetime, timezone
from io import BytesIO

import openpyxl
import pytest
from psycopg.types.json import Jsonb

import db
from analytics.learner_model.bkt.mastery import upsert_raw_responses
from routers import placement_test as placement_test_router
from scripts import import_placement_bkt_workbook as workbook_import
from services import placement_data_import_service


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


def test_admin_placement_data_import_preview_and_sample(admin_client, monkeypatch):
    captured: dict[str, object] = {}

    def preview(_db, content: bytes, filename: str):
        captured.update({"content": content, "filename": filename})
        return {"valid": True, "filename": filename, "rowIssues": [], "responseCount": 2}

    monkeypatch.setattr(placement_test_router.data_import_service, "preview_import", preview)
    preview_response = admin_client.post(
        "/api/admin/placement-test/results/import/preview",
        files={"file": ("responses.xlsx", b"workbook", "application/octet-stream")},
    )
    assert preview_response.status_code == 200
    assert captured == {"content": b"workbook", "filename": "responses.xlsx"}

    monkeypatch.setattr(placement_test_router.data_import_service, "build_sample_workbook", lambda _db: b"xlsx")
    sample_response = admin_client.get("/api/admin/placement-test/results/import/sample")
    assert sample_response.status_code == 200
    assert sample_response.content == b"xlsx"
    assert "placement-responses-sample.xlsx" in sample_response.headers["content-disposition"]


def test_admin_placement_data_import_replace_route(admin_client, monkeypatch):
    captured: dict[str, object] = {}

    def replace(_db, content: bytes, filename: str):
        captured.update({"content": content, "filename": filename})
        return {"valid": True, "filename": filename, "deletedAttempts": 1, "deletedResponses": 2, "responseCount": 2}

    monkeypatch.setattr(placement_test_router.data_import_service, "replace_import", replace)
    response = admin_client.post(
        "/api/admin/placement-test/results/import/replace",
        files={"file": ("responses.xlsx", b"workbook", "application/octet-stream")},
    )
    assert response.status_code == 200
    assert response.json()["deletedAttempts"] == 1
    assert captured == {"content": b"workbook", "filename": "responses.xlsx"}


def test_admin_can_activate_imported_student_logins_without_losing_placement_data(
    admin_client, anonymous_client, monkeypatch,
):
    _seed_import_batch()
    monkeypatch.setattr(workbook_import, "EXPECTED_STUDENT_IDS", ("SIM001",))

    response = admin_client.post(
        "/api/admin/placement-test/results/accounts/activate",
        json={"temporaryPassword": "shared-login-2026"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "activatedAccounts": 1,
        "studentIds": ["SIM001"],
        "testAccounts": True,
    }
    login = anonymous_client.post(
        "/api/students/login",
        json={"studentId": "SIM001", "password": "shared-login-2026"},
    )
    assert login.status_code == 200

    with db.connect_db() as connection:
        student = connection.execute(
            "SELECT password_reset_required, password_version, is_test_account FROM students WHERE id = 'SIM001'"
        ).fetchone()
        attempt_count = connection.execute(
            "SELECT count(*) AS n FROM placement_test_attempts WHERE student_id = 'SIM001'"
        ).fetchone()["n"]
        response_count = connection.execute(
            "SELECT count(*) AS n FROM vocab_quiz_responses WHERE student_id = 'SIM001'"
        ).fetchone()["n"]
        mastery_count = connection.execute(
            "SELECT count(*) AS n FROM student_vocab_mastery WHERE student_id = 'SIM001'"
        ).fetchone()["n"]

    assert student == {"password_reset_required": False, "password_version": 1, "is_test_account": True}
    assert (attempt_count, response_count, mastery_count) == (1, 2, 2)


def test_activating_imported_student_logins_requires_admin(anonymous_client):
    response = anonymous_client.post(
        "/api/admin/placement-test/results/accounts/activate",
        json={"temporaryPassword": "shared-login-2026"},
    )
    assert response.status_code in (401, 403)


_REPLACE_BLUEPRINT_QUESTIONS = [
    {
        "questionId": "Q0016",
        "sourceStoryId": "canonical-story-5-1",
        "sourceWordId": "word-1",
        "targetWord": "自由",
        "position": 1,
        "questionType": "basic_meaning_mcq",
        "answerFormat": "single_choice",
        "round": 1,
        "tier": "tier1",
        "correctAnswer": "to be free",
        "acceptedAnswers": ["to be free"],
        "options": ["to be free", "here", "chair", "window"],
        "prompt": "What does 自由 mean?",
    },
    {
        "questionId": "Q0063",
        "sourceStoryId": "canonical-story-5-2",
        "sourceWordId": "word-2",
        "targetWord": "裡",
        "position": 2,
        "questionType": "context_cloze_mcq",
        "answerFormat": "single_choice",
        "round": 3,
        "tier": "tier3",
        "correctAnswer": "裡",
        "acceptedAnswers": ["裡"],
        "options": ["哥哥", "裡", "房間", "桌子"],
        "prompt": "Choose the missing word.",
    },
]


def _seed_active_blueprint(revision: int) -> None:
    with db.connect_db() as connection:
        connection.execute(
            "INSERT INTO placement_test_blueprints (id, revision, questions, created_at, updated_at) "
            "VALUES ('active', %s, %s, now(), now())",
            (revision, Jsonb(_REPLACE_BLUEPRINT_QUESTIONS)),
        )


def _full_roster_workbook_bytes() -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(list(workbook_import.EXPECTED_HEADERS))
    for student_id in workbook_import.EXPECTED_STUDENT_IDS:
        session_id = f"PLACEMENT-{student_id}-V1"
        student_name = f"Synthetic Student {student_id.removeprefix('SIM')}"
        sheet.append([
            student_id, student_name, session_id, "lesson-5-1",
            "Q0016", "tier1", "to be free", "2026-09-25T00:00:00+00:00", 3000,
        ])
        sheet.append([
            student_id, student_name, session_id, "lesson-5-2",
            "Q0063", "tier3", "裡", "2026-09-25T00:00:00+00:00", 4000,
        ])
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def test_replace_import_clears_a_stale_blueprint_conflict_then_reimports(monkeypatch):
    monkeypatch.setattr(workbook_import, "EXPECTED_QUESTION_COUNT", 2)
    _seed_active_blueprint(revision=2)
    # SIM001 already holds a completed attempt frozen against a stale/empty
    # snapshot, exactly like the "question snapshot differs from the active
    # blueprint" conflict this endpoint exists to clear.
    _seed_import_batch()

    with db.connect_db() as connection:
        result = placement_data_import_service.replace_import(
            connection, _full_roster_workbook_bytes(), "responses.xlsx"
        )

    # SIM001's stale attempt + its 2 responses are what gets cleared; the
    # student account itself is never touched, so it isn't re-"created".
    assert result["deletedStudents"] == 1
    assert result["deletedAttempts"] == 1
    assert result["deletedResponses"] == 2
    assert result["createdStudents"] == 39
    assert result["createdAttempts"] == 40
    assert result["createdResponses"] == 80

    with db.connect_db() as connection:
        attempt = connection.execute(
            "SELECT blueprint_revision FROM placement_test_attempts WHERE id = 'PLACEMENT-SIM001-V1'"
        ).fetchone()
        assert attempt["blueprint_revision"] == 2
        response_count = connection.execute(
            "SELECT count(*) AS n FROM vocab_quiz_responses WHERE student_id = 'SIM001'"
        ).fetchone()
        assert response_count["n"] == 2
        student = connection.execute("SELECT id FROM students WHERE id = 'SIM001'").fetchone()
        assert student is not None


def test_replace_import_rejects_students_outside_the_synthetic_roster(monkeypatch):
    monkeypatch.setattr(workbook_import, "EXPECTED_QUESTION_COUNT", 2)
    _seed_active_blueprint(revision=2)

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(list(workbook_import.EXPECTED_HEADERS))
    sheet.append([
        "REAL001", "A Real Student", "SESSION-1", "lesson-5-1",
        "Q0016", "tier1", "to be free", "2026-09-25T00:00:00+00:00", 3000,
    ])
    output = BytesIO()
    workbook.save(output)
    workbook.close()

    with db.connect_db() as connection:
        with pytest.raises(ValueError, match="Unexpected student_id"):
            placement_data_import_service.replace_import(connection, output.getvalue(), "bad.xlsx")
