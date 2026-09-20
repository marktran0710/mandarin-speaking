from psycopg.types.json import Jsonb

import db


def _publish_word(story_id: str, word_id: str) -> None:
    with db.connect_db() as conn:
        conn.execute(
            """
            INSERT INTO custom_stories (id, title, frames, published, vocab_assessment)
            VALUES (%s, %s, %s, TRUE, %s)
            ON CONFLICT (id) DO UPDATE SET published = TRUE, vocab_assessment = EXCLUDED.vocab_assessment
            """,
            (
                story_id, "BKT debug lesson", Jsonb([]),
                Jsonb([{
                    "questionId": f"{word_id}:know_it:v1",
                    "wordId": word_id,
                    "targetWord": word_id,
                    "level": "easy",
                    "questionType": "basic_meaning_mcq",
                    "answerFormat": "single_choice",
                    "pinyin": "right",
                    "options": ["right", "wrong"],
                    "correctAnswer": "right",
                    "acceptedAnswers": ["right"],
                    "prompt": f"Answer for {word_id}",
                }]),
            ),
        )


def test_inject_requires_admin(logged_in_teacher):
    client, _ = logged_in_teacher
    _publish_word("story-debug-1", "測試")
    response = client.post(
        "/api/admin/bkt-debug/inject",
        json={"studentId": "stu-1", "storyId": "story-debug-1", "wordId": "測試", "pattern": "11"},
    )
    assert response.status_code == 403


def test_inject_rejects_a_malformed_pattern(admin_client):
    _publish_word("story-debug-2", "測試")
    response = admin_client.post(
        "/api/admin/bkt-debug/inject",
        json={"studentId": "stu-1", "storyId": "story-debug-2", "wordId": "測試", "pattern": "1a0"},
    )
    assert response.status_code == 400


def test_inject_404s_for_a_word_with_no_published_easy_item(admin_client):
    _publish_word("story-debug-3", "測試")
    response = admin_client.post(
        "/api/admin/bkt-debug/inject",
        json={"studentId": "stu-1", "storyId": "story-debug-3", "wordId": "沒有", "pattern": "1"},
    )
    assert response.status_code == 404


def test_inject_replays_mastery_step_by_step_and_tags_evidence_synthetic(admin_client):
    _publish_word("story-debug-4", "測試")
    response = admin_client.post(
        "/api/admin/bkt-debug/inject",
        json={"studentId": "stu-debug-4", "storyId": "story-debug-4", "wordId": "測試", "pattern": "0011"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["injectedCount"] == 4
    assert body["correctCount"] == 2
    assert body["totalCount"] == 4
    assert [step["correct"] for step in body["steps"]] == [False, False, True, True]
    # Mastery should end up higher after two correct answers than after two
    # wrong ones - the whole point of a step-by-step trace.
    assert body["steps"][-1]["pLearned"] > body["steps"][1]["pLearned"]
    assert body["finalMastery"] == body["steps"][-1]["pLearned"]

    with db.connect_db() as conn:
        origins = conn.execute(
            "SELECT DISTINCT evidence_origin FROM vocab_quiz_responses WHERE student_id = %s",
            ("stu-debug-4",),
        ).fetchall()
    assert [row["evidence_origin"] for row in origins] == ["synthetic"]


def test_inject_accumulates_across_calls_for_the_same_student_and_word(admin_client):
    _publish_word("story-debug-5", "測試")
    first = admin_client.post(
        "/api/admin/bkt-debug/inject",
        json={"studentId": "stu-debug-5", "storyId": "story-debug-5", "wordId": "測試", "pattern": "1"},
    )
    second = admin_client.post(
        "/api/admin/bkt-debug/inject",
        json={"studentId": "stu-debug-5", "storyId": "story-debug-5", "wordId": "測試", "pattern": "1"},
    )
    assert first.status_code == 200 and second.status_code == 200
    assert second.json()["totalCount"] == 2
