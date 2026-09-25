"""End-to-end proof of Epic 7, Task 7.3: completing the third real core
round through the actual HTTP attempt API schedules an active research
participant's assigned words into vocab_research_probe_assignments - and
does NOT schedule anything for a non-participant."""
from psycopg.types.json import Jsonb

import db
from repositories import research as repo


_MODE_LEVEL = {"tier1": "easy", "tier2": "medium", "tier3": "hard"}


def _publish_attempt_items(attempt: dict) -> None:
    mode = str(attempt.get("mode") or "")
    level = _MODE_LEVEL.get(mode, "easy")
    story_id = str(attempt["storyId"])
    with db.connect_db() as conn:
        row = conn.execute("SELECT vocab_assessment FROM custom_stories WHERE id = %s", (story_id,)).fetchone()
        assessment = list((row or {}).get("vocab_assessment") or [])
        by_identity = {(str(item.get("questionId")), str(item.get("level"))): item for item in assessment if isinstance(item, dict)}
        for result in attempt.get("questionResults") or []:
            item_id = str(result["itemId"])
            word = str(result["word"])
            by_identity[(item_id, level)] = {
                "questionId": item_id, "wordId": word, "targetWord": word, "level": level,
                "questionType": "basic_meaning_mcq" if level == "easy" else "productive_recall",
                "answerFormat": "single_choice" if level == "easy" else "free_text",
                "pinyin": "right", "options": ["right", "wrong"] if level == "easy" else [],
                "correctAnswer": "right", "acceptedAnswers": ["right"], "prompt": f"Answer for {word}",
            }
        merged = list(by_identity.values())
        conn.execute(
            """
            INSERT INTO custom_stories (id, title, frames, published, vocab_assessment)
            VALUES (%s, %s, %s, TRUE, %s)
            ON CONFLICT (id) DO UPDATE SET published = TRUE, vocab_assessment = EXCLUDED.vocab_assessment
            """,
            (story_id, "Probe trigger lesson", Jsonb([]), Jsonb(merged)),
        )


def _post_attempt(client, attempt: dict):
    _publish_attempt_items(attempt)
    return client.post("/api/vocab-quiz-attempts", json=attempt)


def _response(word: str, item_id: str, *, level: str = "easy") -> dict:
    return {
        "word": word, "correct": True, "timeMs": 1200, "itemId": item_id, "conceptId": word,
        "questionKind": "translation", "level": level, "baseStoryId": "probe-lesson-1",
        "itemVersion": "v1", "isBktEligible": True, "diagnosticExposureId": item_id,
        "bktValidationStatus": "APPROVED", "selectedAnswer": "right", "correctAnswer": "right",
        "presentedOptions": ["right", "wrong"], "questionPrompt": word,
    }


def _attempt(attempt_id: str, mode: str, completed_at: str, results: list[dict]) -> dict:
    return {
        "id": attempt_id, "storyId": "probe-lesson-1", "studentName": "Student", "mode": mode,
        "level": "easy", "completedAt": completed_at, "totalQuestions": len(results),
        "correctCount": len(results), "totalTimeMs": sum(r["timeMs"] for r in results),
        "questionResults": results,
    }


def _run_three_core_rounds(client) -> None:
    for index, mode in enumerate(("tier1", "tier2", "tier3"), start=1):
        response = _post_attempt(client, _attempt(f"probe-diag-{index}", mode, f"2026-08-0{index}T00:00:00Z", [
            _response("生詞乙", f"item-b-{index}"),
        ]))
        assert response.status_code == 200, response.text


def test_completing_core_rounds_schedules_a_probe_for_an_active_participant(logged_in_student):
    client, student = logged_in_student
    with db.connect_db() as conn:
        repo.insert_study(
            conn, id="study-probe-trigger", name="Test study", status="active", config_json={},
            policy_version="v1", assignment_version="v1", created_at="2026-01-01T00:00:00Z",
        )
        repo.insert_participant(
            conn, study_id="study-probe-trigger", student_id=student["id"], class_id=None,
            sequence_id="A", active=True, created_at="2026-01-01T00:00:00Z",
        )
        repo.insert_assignment(
            conn, study_id="study-probe-trigger", student_id=student["id"], word_id="生詞乙",
            lesson_id="probe", section_id="probe-lesson-1", bkt_policy="mastery_blind", retention_policy="adaptive_sm2",
            sequence_id="A", related_set_id=None, yoke_source_word_id=None,
            assignment_version="v1", created_at="2026-01-01T00:00:00Z",
        )
        for probe_type in ("probe_7d", "probe_21d", "final_retention"):
            repo.insert_assessment_item(
                conn, id=f"item-生詞乙-{probe_type}", study_id="study-probe-trigger", word_id="生詞乙",
                assessment_type=probe_type, question_type="mc_translation", prompt="What does 生詞乙 mean?",
                choices=["A", "B"], correct_answer="A", created_at="2026-01-01T00:00:00Z",
            )

    _run_three_core_rounds(client)

    with db.connect_db() as conn:
        assignments = repo.find_probe_assignments_for_student(conn, "study-probe-trigger", student["id"])
    assert "生詞乙" in assignments


def test_a_non_participant_never_gets_a_probe_scheduled(logged_in_student):
    client, student = logged_in_student
    _run_three_core_rounds(client)

    with db.connect_db() as conn:
        rows = conn.execute(
            "SELECT COUNT(*) AS total FROM vocab_research_probe_assignments WHERE student_id = %s",
            (student["id"],),
        ).fetchone()
    assert rows["total"] == 0
