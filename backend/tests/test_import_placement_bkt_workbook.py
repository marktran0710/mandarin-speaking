from copy import deepcopy
from datetime import datetime, timezone

import openpyxl
import pytest

import db
from analytics.learner_model.bkt.mastery import upsert_raw_responses
from scripts.import_placement_bkt_workbook import (
    EXPECTED_HEADERS,
    ImportConflictError,
    _existing_state,
    _response_snapshot_matches,
    apply_import,
    build_import_plan,
    delete_previous_import,
    previous_import_counts,
    read_workbook,
)


def _blueprint():
    return {
        "revision": 9,
        "questions": [
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
        ],
    }


def _rows():
    return [
        {
            "student_id": "SIM001",
            "student_name": "Synthetic Student 001",
            "placement_session_id": "PLACEMENT-SIM001-V1",
            "source_story_id": "lesson-5-1",
            "item_id": "Q0016",
            "mode": "tier1",
            "selected_answer": "to be free",
            "answered_at": 1,
            "time_ms": 3000,
        },
        {
            "student_id": "SIM001",
            "student_name": "Synthetic Student 001",
            "placement_session_id": "PLACEMENT-SIM001-V1",
            "source_story_id": "lesson-5-2",
            "item_id": "Q0063",
            "mode": "tier3",
            "selected_answer": "哥哥",
            "answered_at": 2,
            "time_ms": 4000,
        },
        {
            "student_id": "SIM002",
            "student_name": "Synthetic Student 002",
            "placement_session_id": "PLACEMENT-SIM002-V1",
            "source_story_id": "lesson-5-1",
            "item_id": "Q0016",
            "mode": "tier1",
            "selected_answer": "here",
            "answered_at": 3,
            "time_ms": 3001,
        },
        {
            "student_id": "SIM002",
            "student_name": "Synthetic Student 002",
            "placement_session_id": "PLACEMENT-SIM002-V1",
            "source_story_id": "lesson-5-2",
            "item_id": "Q0063",
            "mode": "tier3",
            "selected_answer": "裡",
            "answered_at": 4,
            "time_ms": 4001,
        },
    ]


def test_build_plan_canonicalizes_story_and_grades_from_blueprint():
    plan = build_import_plan(
        _rows(),
        _blueprint(),
        imported_at="2026-09-25T00:00:00+00:00",
        expected_student_ids=("SIM001", "SIM002"),
    )

    assert plan["summary"]["response_count"] == 4
    assert plan["summary"]["correct_count"] == 2
    assert plan["summary"]["incorrect_count"] == 2
    assert plan["summary"]["correct_by_mode"] == {"tier1": 1, "tier3": 1}
    assert plan["response_rows"][0]["lesson_id"] == "canonical-story-5-1"
    assert plan["response_rows"][0]["evidence_origin"] == "synthetic"
    assert plan["response_rows"][0]["resolver_version"] == "placement-workbook-import-v1"
    assert plan["attempts"][0]["response_snapshot"][0]["answeredAt"] == "2026-09-25T00:00:00+00:00"


def test_build_plan_rejects_missing_student_coverage():
    with pytest.raises(ValueError, match="Student coverage mismatch"):
        build_import_plan(
            _rows()[:2],
            _blueprint(),
            imported_at="2026-09-25T00:00:00+00:00",
            expected_student_ids=("SIM001", "SIM002"),
        )


def test_build_plan_rejects_mode_mismatch():
    rows = _rows()
    rows[0] = {**rows[0], "mode": "tier3"}
    with pytest.raises(ValueError, match="does not match active tier"):
        build_import_plan(
            rows,
            _blueprint(),
            imported_at="2026-09-25T00:00:00+00:00",
            expected_student_ids=("SIM001", "SIM002"),
        )


def test_existing_response_snapshot_comparison_ignores_operational_timestamp():
    expected = _rows()[:2]
    left = [
        {
            "questionId": "Q0016",
            "selectedAnswer": expected[0]["selected_answer"],
            "timeMs": expected[0]["time_ms"],
            "answeredAt": "2026-01-01T00:00:00+00:00",
            "correct": True,
            "position": 1,
        },
        {
            "questionId": "Q0063",
            "selectedAnswer": expected[1]["selected_answer"],
            "timeMs": expected[1]["time_ms"],
            "answeredAt": "2026-01-01T00:00:01+00:00",
            "correct": False,
            "position": 2,
        },
    ]
    right = deepcopy(left)
    right[0]["answeredAt"] = "2026-09-25T00:00:00+00:00"
    right[1]["answeredAt"] = "2026-09-25T00:00:00+00:00"
    assert _response_snapshot_matches(left, right)


def test_read_workbook_requires_exact_headers_and_keeps_numeric_time(tmp_path):
    path = tmp_path / "responses.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(EXPECTED_HEADERS)
    sheet.append([
        "SIM001",
        "Synthetic Student 001",
        "PLACEMENT-SIM001-V1",
        "lesson-5-1",
        "Q0016",
        "tier1",
        "to be free",
        46290.1,
        3402,
    ])
    workbook.save(path)
    workbook.close()

    rows = read_workbook(path)
    assert rows[0]["time_ms"] == 3402
    assert rows[0]["selected_answer"] == "to be free"


def _real_response(student_id: str) -> dict:
    return {
        "student_id": student_id, "word_id": "word-1", "word": "自由", "lesson_id": "canonical-story-5-1",
        "quiz_id": "real-quiz", "attempt_id": "real-quiz", "item_id": "Q0016",
        "question_type": "basic_meaning_mcq", "selected_answer": "to be free", "correct_answer": "to be free",
        "presented_options": ["to be free", "here", "chair", "window"], "question_prompt": "What does 自由 mean?",
        "answered_at": "2026-09-01T00:00:00+00:00", "bkt_eligible": True,
        "diagnostic_exposure_id": "real-quiz:Q0016", "bkt_eligibility_errors": [], "correct": True,
        "response_time_ms": 1000, "occurred_at": "2026-09-01T00:00:00+00:00",
        "occurred_at_utc": datetime(2026, 9, 1, tzinfo=timezone.utc), "evidence_origin": "real",
        "resolver_version": "vocab-quiz-v1", "attempt_order": 0, "quiz_level": "tier1", "quiz_mode": "tier1",
        "round_type": "1", "knowledge_dimension": "meaning", "activity_type": "diagnostic",
        "research_study_id": None,
    }


def test_replace_reimports_after_blueprint_change_and_keeps_real_evidence(admin_client):
    def plan_for(blueprint):
        return build_import_plan(
            _rows(), blueprint, imported_at="2026-09-25T00:00:00+00:00",
            expected_student_ids=("SIM001", "SIM002"),
        )

    first = plan_for(_blueprint())
    with db.connect_db() as conn:
        apply_import(conn, first)
        upsert_raw_responses(conn, [_real_response("SIM001")])

    # The admin re-uploads the blueprint with the two questions swapped.
    changed = _blueprint()
    changed["revision"] = 10
    changed["questions"][0]["position"], changed["questions"][1]["position"] = 2, 1
    second = plan_for(changed)
    with db.connect_db() as conn:
        with pytest.raises(ImportConflictError, match="question snapshot differs"):
            _existing_state(conn, second)

    with db.connect_db() as conn:
        assert previous_import_counts(conn, second) == {"attempts": 2, "responses": 4}
        assert delete_previous_import(conn, second) == {"attempts": 2, "responses": 4}
        apply_import(conn, second)

    with db.connect_db() as conn:
        revisions = conn.execute(
            "SELECT DISTINCT blueprint_revision FROM placement_test_attempts WHERE student_id = ANY(%s)",
            (["SIM001", "SIM002"],),
        ).fetchall()
        origins = conn.execute(
            "SELECT evidence_origin, count(*) AS n FROM vocab_quiz_responses "
            "WHERE student_id = ANY(%s) GROUP BY evidence_origin ORDER BY evidence_origin",
            (["SIM001", "SIM002"],),
        ).fetchall()
        assert _existing_state(conn, second)["skip_sessions"] == {"PLACEMENT-SIM001-V1", "PLACEMENT-SIM002-V1"}
    assert [row["blueprint_revision"] for row in revisions] == [10]
    assert [(row["evidence_origin"], row["n"]) for row in origins] == [("real", 1), ("synthetic", 4)]
