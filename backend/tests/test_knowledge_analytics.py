from psycopg.types.json import Jsonb

import database
from routers.knowledge_analytics import _evaluation, _lower_loss_signal


def _insert_attempt(attempt_id: str, student_id: str, story_id: str, completed_at: str, results: list[dict]) -> None:
    with database.connect_db() as db:
        db.execute(
            """
            INSERT INTO vocab_quiz_attempts
                (id, story_id, student_name, student_id, mode, completed_at,
                 total_questions, correct_count, total_time_ms, question_results)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (attempt_id, story_id, "Pilot Student", student_id, "tier1", completed_at,
             len(results), sum(bool(result.get("correct")) for result in results), 1000, Jsonb(results)),
        )


def _eligible_result(word: str, correct: bool, index: int, *, level: str = "easy") -> dict:
    return {
        "word": word,
        "conceptId": word,
        "correct": correct,
        "level": level,
        "itemId": f"item-{index}-{word}",
        "questionKind": "translation",
        "isBktEligible": True,
        "diagnosticExposureId": f"exposure-{index}-{word}",
        "bktValidationStatus": "APPROVED",
    }


def test_knowledge_state_is_admin_only(anonymous_client):
    assert anonymous_client.get("/api/admin/analytics/knowledge-state").status_code == 401


def test_knowledge_state_rejects_teacher_and_student(logged_in_teacher, logged_in_student):
    teacher_client, _ = logged_in_teacher
    assert teacher_client.get("/api/admin/analytics/knowledge-state").status_code == 403

    student_client, _ = logged_in_student
    assert student_client.get("/api/admin/analytics/knowledge-state").status_code == 403


def test_knowledge_state_compares_models_and_applies_filters(admin_client):
    for index in range(12):
        _insert_attempt(
            f"pilot-{index}", "student-1", "story-5-1", f"2026-01-{index + 1:02d}T00:00:00Z",
            [_eligible_result("學習", index % 3 != 0, index),
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
    assert body["dataQuality"]["attemptsWithoutId"] == 0
    assert body["models"]["pfa"]["students"][0]["skills"][0]["conceptId"] == "學習"
    assert body["models"]["pfa"]["evaluation"]["predictionCount"] == 6
    assert body["models"]["pfa"]["masteryInterpretation"] == "predicted_correct_probability"
    assert body["models"]["bkt"]["masteryInterpretation"] == "latent_mastery_probability"


def test_knowledge_state_does_not_select_winner_for_single_class_predictions(admin_client):
    for index in range(12):
        _insert_attempt(
            f"pilot-all-correct-{index}", "student-1", "story-all-correct", f"2026-02-{index + 1:02d}T00:00:00Z",
            [_eligible_result("房間", True, index)],
        )

    body = admin_client.get("/api/admin/analytics/knowledge-state").json()
    assert body["lowerLossSignal"] is None
    assert body["models"]["pfa"]["evaluation"]["status"] == "insufficient_evidence"
    assert body["models"]["pfa"]["evaluation"]["positiveCount"] == 6
    assert body["models"]["pfa"]["evaluation"]["negativeCount"] == 0


def test_knowledge_state_returns_insufficient_data_without_a_winner(admin_client):
    _insert_attempt(
        "pilot-small", "student-1", "story-small", "2026-01-01T00:00:00Z",
        [{"conceptId": "房間", "correct": True, "level": "medium"}],
    )
    body = admin_client.get("/api/admin/analytics/knowledge-state").json()
    assert body["lowerLossSignal"] is None
    assert body["models"]["pfa"]["evaluation"]["status"] == "insufficient_evidence"


def test_lower_loss_signal_reports_no_material_difference_for_a_tie():
    def result(log_loss: float) -> dict:
        return {"evaluation": {"status": "evidence_ready", "logLoss": log_loss}}

    assert _lower_loss_signal(result(0.40), result(0.405)) == "no_material_difference"
    assert _lower_loss_signal(result(0.42), result(0.40)) == "bkt"


def test_evaluation_reports_every_conservative_evidence_check_that_failed():
    result = {
        "train_n": 10,
        "metrics": {"n": 8, "positive_count": 3, "negative_count": 5, "log_loss": 0.5, "brier": 0.2, "calibration_error": 0.1, "auc": 0.6},
        "fit_diagnostics": {"status": "success", "optimizer": "test", "message": "ok", "iterations": 1, "objective": 0.5, "finite": True},
    }
    evaluation = _evaluation(result, {"studentCount": 2, "conceptCount": 3})
    assert evaluation["status"] == "insufficient_evidence"
    assert {check["name"] for check in evaluation["evidenceChecks"] if not check["passed"]} == {
        "training_records", "evaluation_predictions", "evaluation_positives", "evaluation_negatives", "students", "concepts",
    }
