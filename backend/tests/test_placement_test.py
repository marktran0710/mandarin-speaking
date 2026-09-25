from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

import openpyxl
from psycopg.types.json import Jsonb

import db
import security.auth as auth
from analytics.learner_model.bkt.calibration_store import load_calibration_snapshot
from services.placement_test_service import replace_from_upload


def _assessment(story_prefix: str) -> list[dict]:
    return [
        {
            "questionId": f"Q-{story_prefix}-001",
            "wordId": f"{story_prefix}-W001",
            "targetWord": "書",
            "round": 1,
            "tier": "tier1",
            "questionType": "basic_meaning_mcq",
            "answerFormat": "single_choice",
            "pinyin": "shū",
            "options": ["book", "chair", "room", "teacher"],
            "correctAnswer": "book",
            "acceptedAnswers": ["book"],
            "prompt": "What does this word mean?",
        },
        {
            "questionId": f"Q-{story_prefix}-002",
            "wordId": f"{story_prefix}-W002",
            "targetWord": "你好",
            "round": 2,
            "tier": "tier2",
            "questionType": "character_to_pinyin_typing",
            "answerFormat": "free_text",
            "pinyin": "nǐ hǎo",
            "options": [],
            "correctAnswer": "nǐ hǎo",
            "acceptedAnswers": ["nǐ hǎo"],
            "prompt": "Type the pinyin.",
        },
        {
            "questionId": f"Q-{story_prefix}-003",
            "wordId": f"{story_prefix}-W003",
            "targetWord": "家",
            "round": 3,
            "tier": "tier3",
            "questionType": "context_cloze_mcq",
            "answerFormat": "single_choice",
            "pinyin": "jiā",
            "options": ["家", "學校", "書", "椅子"],
            "correctAnswer": "家",
            "acceptedAnswers": ["家"],
            "prompt": "我回到___。",
        },
    ]


def _publish(story_id: str, prefix: str, *, published: bool = True) -> None:
    with db.connect_db() as conn:
        conn.execute(
            """
            INSERT INTO custom_stories (id, title, frames, published, vocab_assessment)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (story_id, f"Placement {prefix}", Jsonb([]), published, Jsonb(_assessment(prefix))),
        )


def _student_session(admin_client, name: str = "Placement Student"):
    student = admin_client.post("/api/students", json={"name": name, "password": "placement-password"}).json()
    admin_client.cookies.clear()
    admin_client.cookies.set(
        auth.ROLE_COOKIE_NAMES["student"],
        auth.issue_token("student", student["id"]),
        domain="testserver.local",
        path="/",
    )
    admin_client.headers[auth.CLIENT_ROLE_HEADER] = "student"
    return student


def test_placement_preview_is_read_only_and_resolves_order_across_published_stories(admin_client):
    _publish("placement-story-1", "C5-5-1-I1")
    _publish("placement-story-2", "C5-6-1-I2")
    content = (
        "Word Key,Round\n"
        "C5-6-1-I2-W003,3\n"
        "C5-5-1-I1-W001,1\n"
    ).encode()

    response = admin_client.post(
        "/api/admin/placement-test/import/preview",
        files={"file": ("placement.csv", content, "text/csv")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert [question["questionId"] for question in body["questions"]] == [
        "Q-C5-6-1-I2-003", "Q-C5-5-1-I1-001",
    ]
    assert "correctAnswer" not in body["questions"][0]
    with db.connect_db() as conn:
        assert conn.execute("SELECT COUNT(*) AS count FROM placement_test_blueprints").fetchone()["count"] == 0

    confirm = admin_client.post(
        "/api/admin/placement-test/import/confirm",
        files={"file": ("placement.csv", content, "text/csv")},
    )
    assert confirm.status_code == 200
    assert confirm.json()["questionCount"] == 2

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Questions"
    sheet.append(["Word Key", "Round"])
    sheet.append(["C5-5-1-I1-W002", 2])
    xlsx = BytesIO()
    workbook.save(xlsx)
    xlsx_preview = admin_client.post(
        "/api/admin/placement-test/import/preview",
        files={"file": ("placement.xlsx", xlsx.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert xlsx_preview.status_code == 200
    assert xlsx_preview.json()["valid"] is True
    assert xlsx_preview.json()["questions"][0]["questionId"] == "Q-C5-5-1-I1-002"


def test_placement_grades_from_snapshot_and_writes_real_diagnostic_bkt_evidence(admin_client):
    _publish("placement-story-all", "ALL")
    content = "Word Key,Round\nALL-W001,1\nALL-W002,2\nALL-W003,3\n".encode()
    assert admin_client.post(
        "/api/admin/placement-test/import/confirm",
        files={"file": ("placement.csv", content, "text/csv")},
    ).status_code == 200
    student = _student_session(admin_client)

    started = admin_client.post("/api/placement-test/attempts")
    assert started.status_code == 200
    attempt = started.json()
    assert [question["position"] for question in attempt["questions"]] == [1, 2, 3]
    with db.connect_db() as conn:
        replace_from_upload(conn, b"Word Key,Round\nALL-W001,1\n", "replacement.csv")

    completed = admin_client.post(
        f"/api/placement-test/attempts/{attempt['attemptId']}/complete",
        json={
            "responses": [
                {"questionId": "Q-ALL-001", "selectedAnswer": "wrong", "correct": True, "timeMs": 10},
                {"questionId": "Q-ALL-002", "selectedAnswer": "ni3 hao3", "timeMs": 20},
                {"questionId": "Q-ALL-003", "selectedAnswer": "家", "timeMs": 30},
            ],
            "completedAt": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert completed.status_code == 200
    assert completed.json()["correctCount"] == 2
    assert completed.json()["percentage"] == 67
    assert completed.json()["messageKey"] == "KEEP_PRACTICING"

    with db.connect_db() as conn:
        rows = conn.execute(
            "SELECT question_type, correct, activity_type, evidence_origin, bkt_eligible, "
            "resolver_version, quiz_level, quiz_mode FROM vocab_quiz_responses "
            "WHERE student_id = %s ORDER BY attempt_order",
            (student["id"],),
        ).fetchall()
        assert len(rows) == 3
        assert [row["correct"] for row in rows] == [False, True, True]
        assert {row["activity_type"] for row in rows} == {"diagnostic"}
        assert {row["evidence_origin"] for row in rows} == {"real"}
        assert {row["resolver_version"] for row in rows} == {"placement-assessment-v1"}
        assert [row["quiz_level"] for row in rows] == ["tier1", "tier2", "tier3"]
        mastery = conn.execute(
            "SELECT word_id, observation_count FROM student_vocab_mastery WHERE student_id = %s ORDER BY word_id",
            (student["id"],),
        ).fetchall()
        assert len(mastery) == 3
        snapshot = load_calibration_snapshot(conn, "real", student_id=student["id"])
        assert len(snapshot.records) == 3
        assert snapshot.resolver_versions == ("placement-assessment-v1",)
        stored_attempt = conn.execute(
            "SELECT blueprint_revision, question_snapshot FROM placement_test_attempts WHERE id = %s",
            (attempt["attemptId"],),
        ).fetchone()
        assert stored_attempt["blueprint_revision"] == 1
        assert [question["questionId"] for question in stored_attempt["question_snapshot"]] == [
            "Q-ALL-001", "Q-ALL-002", "Q-ALL-003",
        ]


def test_placement_rejects_duplicate_unknown_unpublished_and_ambiguous_ids(admin_client):
    _publish("placement-published", "PUBLISHED")
    _publish("placement-hidden", "HIDDEN", published=False)
    _publish("placement-ambiguous-1", "AMBIGUOUS")
    _publish("placement-ambiguous-2", "AMBIGUOUS")
    cases = [
        ("PUBLISHED-W001,1\nPUBLISHED-W001,1", "Duplicate"),
        ("UNKNOWN-W001,1", "Unknown"),
        ("HIDDEN-W001,1", "unpublished"),
        ("AMBIGUOUS-W001,1", "Ambiguous"),
    ]
    for question_id, expected in cases:
        response = admin_client.post(
            "/api/admin/placement-test/import/preview",
            files={"file": ("placement.csv", f"Word Key,Round\n{question_id}\n".encode(), "text/csv")},
        )
        assert response.status_code == 200
        assert response.json()["valid"] is False
        assert expected.casefold() in response.json()["rowIssues"][0].casefold()
