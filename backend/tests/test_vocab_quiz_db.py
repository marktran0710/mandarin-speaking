"""Quiz attempts and the weak-words query against PostgreSQL JSONB."""
import contextlib

from conftest import login_new_client


def _attempt(attempt_id: str, completed_at: str, results: list, **overrides) -> dict:
    payload = {
        "id": attempt_id,
        "storyId": "teacher-story-1",
        "studentName": "Mai",
        "mode": "tier2",
        "completedAt": completed_at,
        "totalQuestions": len(results),
        "correctCount": sum(1 for r in results if r["correct"]),
        "totalTimeMs": sum(r["timeMs"] for r in results),
        "questionResults": results,
    }
    payload.update(overrides)
    return payload


def test_attempt_round_trips_with_question_results(logged_in_student):
    client, _ = logged_in_student
    attempt = _attempt("att-1", "2026-07-26T08:00:00Z", [
        {"word": "房間", "correct": True, "timeMs": 1200},
        {"word": "桌子", "correct": False, "timeMs": 3400},
    ])
    assert client.post("/api/vocab-quiz-attempts", json=attempt).status_code == 200

    saved = client.get("/api/vocab-quiz-attempts", params={"story_id": "teacher-story-1"}).json()
    assert len(saved) == 1
    assert saved[0]["questionResults"][0]["word"] == "房間"
    assert saved[0]["correctCount"] == 1
    assert saved[0]["mode"] == "tier2"


def test_attempts_filter_by_student_id(logged_in_student):
    client, student = logged_in_student
    client.post("/api/vocab-quiz-attempts", json=_attempt(
        "att-1", "2026-07-26T08:00:00Z",
        [{"word": "房間", "correct": True, "timeMs": 1000}]))

    with contextlib.ExitStack() as stack:
        an_client, _ = login_new_client(stack, "An", "student")
        an_client.post("/api/vocab-quiz-attempts", json=_attempt(
            "att-2", "2026-07-26T09:00:00Z",
            [{"word": "床", "correct": True, "timeMs": 1000}],
            studentName="An"))

        teacher_client, _ = login_new_client(stack, "Reviewer", "teacher", password="teach123")
        mine = teacher_client.get(
            "/api/vocab-quiz-attempts", params={"student_id": student["id"]}
        ).json()

    assert [a["id"] for a in mine] == ["att-1"]


def test_weak_words_uses_the_most_recent_answer(logged_in_student):
    client, _ = logged_in_student
    client.post("/api/vocab-quiz-attempts", json=_attempt(
        "att-old", "2026-07-25T08:00:00Z", [
            {"word": "房間", "correct": False, "timeMs": 4000},
            {"word": "桌子", "correct": False, "timeMs": 4000},
        ]))
    client.post("/api/vocab-quiz-attempts", json=_attempt(
        "att-new", "2026-07-26T08:00:00Z", [
            {"word": "房間", "correct": True, "timeMs": 1100},
        ]))

    weak = client.get("/api/vocab-quiz-attempts/weak-words", params={
        "story_id": "teacher-story-1"}).json()
    # These legacy attempts do not carry the approved three-round diagnostic
    # contract, so they remain audit-only and cannot create recommendations.
    assert weak["words"] == []


def test_weak_words_requires_login(anonymous_client):
    response = anonymous_client.get("/api/vocab-quiz-attempts/weak-words", params={
        "story_id": "teacher-story-1"})
    assert response.status_code == 401


def test_frex_analytics_reads_question_results_from_jsonb(logged_in_student):
    """The analytics loaders stopped calling json.loads — this proves they
    still see the per-question data, end to end through the real endpoint."""
    client, student = logged_in_student

    client.post("/api/vocab-quiz-attempts", json=_attempt(
        "att-1", "2026-07-26T08:00:00Z", [
            {"word": "房間", "correct": False, "timeMs": 4000},
            {"word": "桌子", "correct": True, "timeMs": 1100},
        ]))

    response = client.get("/api/analytics/vocab-quiz/frex", params={"top": 5})
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["studentId"] == student["id"]
    assert "房間" in [w["word"] for w in rows[0]["words"]]


def test_frex_analytics_on_an_empty_database(client):
    """The Insights tab blanks out entirely on a non-200, so no data must
    still be a well-formed empty response, not a 500."""
    response = client.get("/api/analytics/vocab-quiz/frex")
    assert response.status_code == 200
    assert response.json() == []
