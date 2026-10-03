"""Development-only date/interval overrides for fast spaced-repetition UI checks."""
from dataclasses import replace
from datetime import date, datetime, timezone

import main  # noqa: F401  # Loads the router facade before the test patches it.
from routers import vocab_quiz_attempts as attempt_routes
from routers import vocab_quiz_mastery as mastery_routes
from routers import vocab_review_sessions as review_session_routes
from services import vocab_quiz_attempt_service as attempt_service


def _review_attempt(attempt_id: str) -> dict:
    return {
        "id": attempt_id,
        "storyId": "srs-override-lesson",
        "studentName": "Student",
        "mode": "maintenance_review",
        "completedAt": "2026-09-16T00:00:00Z",
        "totalQuestions": 1,
        "correctCount": 1,
        "totalTimeMs": 900,
        "questionResults": [{"word": "學習", "conceptId": "學習", "correct": True, "timeMs": 900}],
    }


def test_development_today_override_reaches_review_queue(logged_in_student, monkeypatch):
    client, student = logged_in_student
    captured = []

    def fake_queue(db, student_id, options, now=None):
        captured.append((student_id, options, now))
        return {"queue": []}

    monkeypatch.setattr(mastery_routes, "build_review_queue", fake_queue)

    response = client.get(f"/api/students/{student['id']}/review-queue?today=2026-09-17")

    assert response.status_code == 200
    assert captured == [(student["id"], {}, datetime(2026, 9, 17, tzinfo=timezone.utc))]


def test_today_override_is_ignored_when_missing_malformed_or_not_development(logged_in_student, monkeypatch):
    client, student = logged_in_student
    captured = []

    def fake_queue(db, student_id, options, now=None):
        captured.append(now)
        return {"queue": []}

    monkeypatch.setattr(mastery_routes, "build_review_queue", fake_queue)
    assert client.get(f"/api/students/{student['id']}/review-queue").status_code == 200
    for invalid in ("tomorrow", "2026-09-17junk", "2026-02-30", "2026-9-17"):
        assert client.get(f"/api/students/{student['id']}/review-queue?today={invalid}").status_code == 200
    base_settings = attempt_routes.settings
    for app_env in ("production", "staging", "unknown"):
        monkeypatch.setattr(attempt_routes, "settings", replace(base_settings, app_env=app_env))
        assert client.get(f"/api/students/{student['id']}/review-queue?today=2026-09-17").status_code == 200

    assert captured == [None] * 8


def test_legacy_client_selected_maintenance_is_rejected(logged_in_student, monkeypatch):
    client, _ = logged_in_student
    captured = []

    def fake_apply(db, student_id, question_results, now=None, day_seconds=86400.0):
        captured.append(now)
        return 0

    monkeypatch.setattr(attempt_service, "apply_srs_updates", fake_apply)

    completed = client.post("/api/vocab-quiz-attempts?today=2026-09-17", json=_review_attempt("srs-completed"))
    partial = client.post("/api/vocab-quiz-responses?today=2026-09-23", json=_review_attempt("srs-partial"))

    assert completed.status_code == 409 and partial.status_code == 409
    assert completed.json()["detail"]["code"] == "SERVER_SELECTED_REVIEW_REQUIRED"
    assert captured == []


def test_review_session_owns_date_and_interval_overrides(logged_in_student, monkeypatch):
    client, student = logged_in_student
    captured = []

    def fake_answer(db, student_id, session_id, slot_id, selected_answer, response_time_ms, *, now, day_seconds):
        captured.append((now, day_seconds))
        return {"accepted": True}

    monkeypatch.setattr(review_session_routes.service, "answer_review_session_question", fake_answer)
    monkeypatch.setattr(attempt_routes, "settings", replace(
        attempt_routes.settings, app_env="development", srs_day_seconds=60.0,
    ))

    response = client.post(
        f"/api/students/{student['id']}/review-sessions/session-1/answers?today=2026-09-17",
        json={"slotId": "slot-1", "selectedAnswer": "answer", "responseTimeMs": 500},
    )

    assert response.status_code == 200, response.text
    assert captured == [(datetime(2026, 9, 17, tzinfo=timezone.utc), 60.0)]


def test_production_review_session_ignores_date_and_day_seconds_overrides(logged_in_student, monkeypatch):
    client, student = logged_in_student
    captured = []

    def fake_answer(db, student_id, session_id, slot_id, selected_answer, response_time_ms, *, now, day_seconds):
        captured.append((now, day_seconds))
        return {"accepted": True}

    monkeypatch.setattr(review_session_routes.service, "answer_review_session_question", fake_answer)
    monkeypatch.setattr(attempt_routes, "settings", replace(
        attempt_routes.settings, app_env="production", srs_day_seconds=60.0,
    ))

    response = client.post(
        f"/api/students/{student['id']}/review-sessions/session-1/answers?today=2026-09-17",
        json={"slotId": "slot-1", "selectedAnswer": "answer", "responseTimeMs": 500},
    )

    assert response.status_code == 200, response.text
    assert len(captured) == 1
    assert captured[0][0].date() != date(2026, 9, 17)
    assert captured[0][1] == 86400.0
