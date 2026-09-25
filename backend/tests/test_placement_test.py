from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

import openpyxl
import pytest
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


def test_placement_answers_produce_hand_computed_bkt_mastery(admin_client):
    # Expected values are worked out by hand from BKT_CONFIG (prior 0.20,
    # learn 0.15, MCQ guess/slip 0.20/0.10, typed 0.05/0.15) rather than by
    # calling the replay code, so this pins the placement -> ledger -> cache
    # flow end to end, not just the row counts.
    _publish("placement-story-bkt", "BKT")
    content = "Word Key,Round\nBKT-W001,1\nBKT-W002,2\nBKT-W003,3\n".encode()
    assert admin_client.post(
        "/api/admin/placement-test/import/confirm",
        files={"file": ("placement.csv", content, "text/csv")},
    ).status_code == 200
    student = _student_session(admin_client, "Placement BKT Student")
    attempt = admin_client.post("/api/placement-test/attempts").json()
    payload = {
        "responses": [
            {"questionId": "Q-BKT-001", "selectedAnswer": "chair", "timeMs": 10},
            {"questionId": "Q-BKT-002", "selectedAnswer": "ni3 hao3", "timeMs": 20},
            {"questionId": "Q-BKT-003", "selectedAnswer": "家", "timeMs": 30},
        ],
        "completedAt": datetime.now(timezone.utc).isoformat(),
    }
    url = f"/api/placement-test/attempts/{attempt['attemptId']}/complete"
    assert admin_client.post(url, json=payload).json()["correctCount"] == 2
    # A resubmitted attempt must not add a second observation per word.
    assert admin_client.post(url, json=payload).status_code == 200

    with db.connect_db() as conn:
        mastery = {
            row["word_id"]: row
            for row in conn.execute(
                "SELECT word_id, p_learned, observation_count, correct_count, incorrect_count "
                "FROM student_vocab_mastery WHERE student_id = %s",
                (student["id"],),
            ).fetchall()
        }
    expected = {
        # MCQ wrong: 0.02 / 0.66 = 0.030303 -> + 0.969697 * 0.15
        "BKT-W001": (0.175758, 0, 1),
        # typed correct: 0.17 / 0.21 = 0.809524 -> + 0.190476 * 0.15
        "BKT-W002": (0.838095, 1, 0),
        # cloze MCQ correct: 0.18 / 0.34 = 0.529412 -> + 0.470588 * 0.15
        "BKT-W003": (0.600000, 1, 0),
    }
    assert set(mastery) == set(expected)
    for word_id, (p_learned, correct_count, incorrect_count) in expected.items():
        row = mastery[word_id]
        assert abs(row["p_learned"] - p_learned) < 1e-6, word_id
        assert row["observation_count"] == 1
        assert (row["correct_count"], row["incorrect_count"]) == (correct_count, incorrect_count)


def _publish_chapter(chapter: int) -> None:
    # Seven placement-tested words plus one word placement never asks about.
    words = [f"C{chapter}-W{index}" for index in range(1, 9)]
    assessment = [
        {
            "questionId": f"Q-{word}",
            "wordId": word,
            "targetWord": word,
            "round": 1,
            "tier": "tier1",
            "questionType": "basic_meaning_mcq",
            "answerFormat": "single_choice",
            "options": ["yes", "no", "maybe", "never"],
            "correctAnswer": "yes",
            "acceptedAnswers": ["yes"],
            "prompt": "What does this word mean?",
        }
        for word in words
    ]
    with db.connect_db() as conn:
        conn.execute(
            """
            INSERT INTO custom_stories (id, title, frames, published, lesson_number, vocab_assessment)
            VALUES (%s, %s, %s, TRUE, %s, %s)
            """,
            (f"placement-chapter-{chapter}", f"Chapter {chapter}", Jsonb([]), chapter, Jsonb(assessment)),
        )


def test_real_placement_attempt_sets_chapter_priors_for_untested_words(admin_client):
    # Full production path: admin imports a 28-question blueprint (7 per
    # chapter 5-8), the student completes it through the API, and words
    # placement never asked about start from their chapter's prior
    # 0.5 * (correct / 7) + 0.5 * 0.20 instead of the global 0.20.
    for chapter in (5, 6, 7, 8):
        _publish_chapter(chapter)
    blueprint = "Word Key,Round\n" + "".join(
        f"C{chapter}-W{index},1\n" for chapter in (5, 6, 7, 8) for index in range(1, 8)
    )
    assert admin_client.post(
        "/api/admin/placement-test/import/confirm",
        files={"file": ("placement.csv", blueprint.encode(), "text/csv")},
    ).status_code == 200
    student = _student_session(admin_client, "Placement Prior Student")

    # Before placement, the student already answered untested chapter-5 word
    # C5-W8 correctly in an ordinary tier1 quiz.
    from analytics.learner_model.bkt.mastery import get_vocabulary_mastery, upsert_raw_responses

    with db.connect_db() as conn:
        upsert_raw_responses(conn, [{
            "student_id": student["id"], "word_id": "C5-W8", "word": "C5-W8",
            "lesson_id": "placement-chapter-5", "quiz_id": "earlier-quiz", "attempt_id": "earlier-quiz",
            "item_id": "Q-C5-W8", "question_type": "basic_meaning_mcq", "selected_answer": "yes",
            "correct_answer": "yes", "presented_options": ["yes", "no", "maybe", "never"],
            "question_prompt": "What does this word mean?", "answered_at": "2026-01-01T00:00:00+00:00",
            "bkt_eligible": True, "diagnostic_exposure_id": "earlier-quiz:Q-C5-W8",
            "bkt_eligibility_errors": [], "correct": True, "response_time_ms": 1000,
            "occurred_at": "2026-01-01T00:00:00+00:00",
            "occurred_at_utc": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "evidence_origin": "real", "resolver_version": "test", "attempt_order": 0,
            "quiz_level": "tier1", "quiz_mode": "tier1", "round_type": "1",
            "knowledge_dimension": "meaning", "activity_type": "diagnostic", "research_study_id": None,
        }])

    attempt = admin_client.post("/api/placement-test/attempts").json()
    correct_per_chapter = {5: 7, 6: 5, 7: 2, 8: 0}
    responses = [
        {
            "questionId": question["questionId"],
            "selectedAnswer": "yes"
            if int(question["questionId"].split("-W")[1]) <= correct_per_chapter[int(question["questionId"][3])]
            else "no",
            "timeMs": 1000,
        }
        for question in attempt["questions"]
    ]
    completed = admin_client.post(
        f"/api/placement-test/attempts/{attempt['attemptId']}/complete",
        json={"responses": responses, "completedAt": datetime.now(timezone.utc).isoformat()},
    )
    assert completed.status_code == 200
    assert completed.json()["correctCount"] == 14

    with db.connect_db() as conn:
        live = {row["wordId"]: row for row in get_vocabulary_mastery(conn, student["id"])}
        cached = conn.execute(
            "SELECT p_learned FROM student_vocab_mastery WHERE student_id = %s AND word_id = 'C5-W8'",
            (student["id"],),
        ).fetchone()

    # Untested words: prior only, no evidence, still NOT_ASSESSED.
    assert live["C6-W8"]["pLearned"] == pytest.approx(0.5 * 5 / 7 + 0.1)  # 0.457143
    assert live["C7-W8"]["pLearned"] == pytest.approx(0.5 * 2 / 7 + 0.1)  # 0.242857
    assert live["C8-W8"]["pLearned"] == pytest.approx(0.1)
    for word_id in ("C6-W8", "C7-W8", "C8-W8"):
        assert live[word_id]["observationCount"] == 0
        assert live[word_id]["status"] == "NOT_ASSESSED"
    # Directly tested words ignore the chapter prior: 0.20 -> one MCQ answer.
    assert live["C5-W1"]["pLearned"] == pytest.approx(0.6)
    assert live["C8-W1"]["pLearned"] == pytest.approx(0.175758, abs=1e-6)
    # C5-W8 starts from the chapter-5 prior 0.6 and then gets one correct MCQ:
    # 0.54 / 0.62 = 0.870968 -> + 0.129032 * 0.15 = 0.890323.
    assert live["C5-W8"]["pLearned"] == pytest.approx(0.890323, abs=1e-6)
    # The rebuilt cache must agree with the live projection.
    assert cached["p_learned"] == pytest.approx(live["C5-W8"]["pLearned"])
