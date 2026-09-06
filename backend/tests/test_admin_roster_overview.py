"""The consolidated admin roster-overview endpoint returns the same data the
console used to fetch as three separate calls (students, teachers, quiz
attempts), in one request, and stays admin-only."""
import contextlib

from conftest import login_new_client


def test_roster_overview_bundles_students_teachers_and_attempts(admin_client):
    admin_client.post("/api/students", json={"name": "Overview Student", "password": "pw-123456"})
    admin_client.post("/api/teachers", json={"name": "Overview Teacher", "password": "pw-123456"})

    overview = admin_client.get("/api/admin/roster-overview")
    assert overview.status_code == 200
    body = overview.json()

    # Shapes are field-for-field identical to the standalone endpoints, so the
    # client can drop the three-call fan-out with no other change.
    assert body["students"] == admin_client.get("/api/students").json()
    assert body["teachers"] == admin_client.get("/api/teachers").json()
    assert body["quizAttempts"] == admin_client.get("/api/vocab-quiz-attempts").json()

    assert any(s["name"] == "Overview Student" for s in body["students"])
    assert any(t["name"] == "Overview Teacher" for t in body["teachers"])


def test_roster_overview_includes_full_quiz_attempt_question_results(admin_client):
    """Admin analytics read per-question data, so attempts keep questionResults."""
    with contextlib.ExitStack() as stack:
        student_client, student = login_new_client(stack, "Quiz Taker", "student")
        student_client.post(
            "/api/vocab-quiz-attempts",
            json={
                "id": "attempt-overview-1",
                "storyId": "story-1",
                "studentName": "Quiz Taker",
                "mode": "standard",
                "completedAt": "2026-09-06T00:00:00Z",
                "totalQuestions": 1,
                "correctCount": 1,
                "totalTimeMs": 1000,
                "questionResults": [
                    {"word": "你好", "correct": True, "timeMs": 1000, "questionKind": "translation"}
                ],
            },
        )

        attempts = admin_client.get("/api/admin/roster-overview").json()["quizAttempts"]

    saved = next(a for a in attempts if a["id"] == "attempt-overview-1")
    assert saved["questionResults"], "questionResults must be preserved for admin analytics"


def test_roster_overview_requires_admin():
    with contextlib.ExitStack() as stack:
        student_client, _ = login_new_client(stack, "Not Admin", "student")
        teacher_client, _ = login_new_client(stack, "Teacher X", "teacher", password="teach123")
        assert student_client.get("/api/admin/roster-overview").status_code == 403
        assert teacher_client.get("/api/admin/roster-overview").status_code == 403
