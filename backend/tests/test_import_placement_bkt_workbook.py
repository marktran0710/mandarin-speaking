from copy import deepcopy

import openpyxl
import pytest

from scripts.import_placement_bkt_workbook import (
    EXPECTED_HEADERS,
    _response_snapshot_matches,
    build_import_plan,
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
