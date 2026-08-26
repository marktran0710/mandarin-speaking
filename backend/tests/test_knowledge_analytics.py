from psycopg.types.json import Jsonb

import database


def _insert_attempt(attempt_id: str, student_id: str, story_id: str, completed_at: str, results: list[dict]) -> None:
    with database.connect_db() as db:
        db.execute(
            """
            INSERT INTO vocab_quiz_attempts
                (id, story_id, student_name, student_id, completed_at,
                 total_questions, correct_count, total_time_ms, question_results)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (attempt_id, story_id, "Pilot Student", student_id, completed_at,
             len(results), sum(bool(result.get("correct")) for result in results), 1000, Jsonb(results)),
        )


def test_knowledge_state_is_admin_only(anonymous_client):
    assert anonymous_client.get("/api/admin/analytics/knowledge-state").status_code == 401


def test_knowledge_state_compares_models_and_applies_filters(admin_client):
    for index in range(12):
        _insert_attempt(
            f"pilot-{index}", "student-1", "story-5-1", f"2026-01-{index + 1:02d}T00:00:00Z",
            [{"word": "學習", "correct": index % 3 != 0, "level": "easy"},
             {"conceptId": "朋友", "correct": True, "level": "hard"}],
        )

    response = admin_client.get(
        "/api/admin/analytics/knowledge-state",
        params={"model": "compare", "story_id": "story-5-1", "level": "easy"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "compare"
    assert set(body["models"]) == {"pfa", "bkt"}
    assert body["dataQuality"]["eligibleResponses"] == 12
    assert body["dataQuality"]["skillCount"] == 1
    assert body["models"]["pfa"]["students"][0]["skills"][0]["conceptId"] == "學習"
    assert body["models"]["pfa"]["evaluation"]["predictionCount"] == 6


def test_knowledge_state_returns_insufficient_data_without_a_winner(admin_client):
    _insert_attempt(
        "pilot-small", "student-1", "story-small", "2026-01-01T00:00:00Z",
        [{"conceptId": "房間", "correct": True, "level": "medium"}],
    )
    body = admin_client.get("/api/admin/analytics/knowledge-state").json()
    assert body["recommendedModel"] is None
    assert body["models"]["pfa"]["evaluation"]["status"] == "insufficient_data"
