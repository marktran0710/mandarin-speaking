from conftest import login_new_client
from dataclasses import replace
from datetime import datetime, timezone
from psycopg.types.json import Jsonb
from types import SimpleNamespace

import db
import pytest
from services.vocab_quiz_attempt_service import _srs_event_results


_MODE_LEVEL = {"tier1": "easy", "tier2": "medium", "tier3": "hard", "weak_words": "easy"}


def test_srs_source_identity_uses_server_response_order_not_client_question_index():
    attempt = SimpleNamespace(id="completed-transport-id")
    first = _srs_event_results(attempt, [
        {"quizId": "stable-round", "questionIndex": 99},
        {"quizId": "stable-round", "questionIndex": 100},
    ])
    replay = _srs_event_results(attempt, [
        {"quizId": "stable-round", "questionIndex": 0},
        {"quizId": "stable-round", "questionIndex": 1},
    ])

    assert [row["sourceResponseId"] for row in first] == ["stable-round:0", "stable-round:1"]
    assert [row["sourceResponseId"] for row in replay] == ["stable-round:0", "stable-round:1"]


def _publish_attempt_items(attempt: dict) -> None:
    """Create the immutable assessment source the API must resolve against."""
    mode = str(attempt.get("mode") or "")
    level = _MODE_LEVEL.get(mode, "easy")
    story_id = str(attempt["storyId"])
    with db.connect_db() as conn:
        row = conn.execute(
            "SELECT vocab_assessment FROM custom_stories WHERE id = %s",
            (story_id,),
        ).fetchone()
        assessment = list((row or {}).get("vocab_assessment") or [])
        by_identity = {
            (str(item.get("questionId")), str(item.get("level"))): item
            for item in assessment
            if isinstance(item, dict)
        }
        for result in attempt.get("questionResults") or []:
            item_id = str(result["itemId"])
            word = str(result["word"])
            by_identity[(item_id, level)] = {
                "questionId": item_id,
                "wordId": word,
                "targetWord": word,
                "level": level,
                "questionType": "basic_meaning_mcq" if level == "easy" else "productive_recall",
                "answerFormat": "single_choice" if level == "easy" else "free_text",
                "pinyin": "right",
                "options": ["right", "wrong"] if level == "easy" else [],
                "correctAnswer": "right",
                "acceptedAnswers": ["right"],
                "prompt": f"Answer for {word}",
            }
        merged = list(by_identity.values())
        conn.execute(
            """
            INSERT INTO custom_stories (id, title, frames, published, vocab_assessment)
            VALUES (%s, %s, %s, TRUE, %s)
            ON CONFLICT (id) DO UPDATE SET published = TRUE, vocab_assessment = EXCLUDED.vocab_assessment
            """,
            (story_id, "BKT test lesson", Jsonb([]), Jsonb(merged)),
        )


def _post_attempt(client, attempt: dict, *, partial: bool = False, today: str | None = None):
    _publish_attempt_items(attempt)
    with db.connect_db() as conn:
        version = conn.execute(
            "SELECT vocabulary_version FROM custom_stories WHERE id = %s",
            (attempt["storyId"],),
        ).fetchone()["vocabulary_version"]
    attempt = {**attempt, "vocabularyVersion": version}
    endpoint = "/api/vocab-quiz-responses" if partial else "/api/vocab-quiz-attempts"
    params = {"today": today} if today else None
    return client.post(endpoint, params=params, json=attempt)


def _response(word: str, correct: bool, item_id: str, *, level: str = "easy", eligible: bool = True, question_kind: str = "translation") -> dict:
    return {
        "word": word,
        "correct": correct,
        "timeMs": 1200,
        "itemId": item_id,
        "conceptId": word,
        "questionKind": question_kind,
        "level": level,
        "baseStoryId": "lesson-1",
        "itemVersion": "v1",
        "isBktEligible": eligible,
        "diagnosticExposureId": item_id if eligible else None,
        "bktValidationStatus": "APPROVED" if eligible else "DRAFT",
        "selectedAnswer": "right" if correct else "wrong",
        "correctAnswer": "right",
        "presentedOptions": ["right", "wrong"],
        "questionPrompt": word,
    }


def _attempt(attempt_id: str, mode: str, completed_at: str, results: list[dict]) -> dict:
    return {
        "id": attempt_id,
        "storyId": "lesson-1",
        "studentName": "Student",
        "mode": mode,
        "level": "easy",
        "completedAt": completed_at,
        "totalQuestions": len(results),
        "correctCount": sum(1 for result in results if result["correct"]),
        "totalTimeMs": sum(result["timeMs"] for result in results),
        "questionResults": results,
    }


def test_bkt_unlocks_after_three_easy_diagnostic_quizzes_and_ranks_bottom_k(logged_in_student):
    client, student = logged_in_student
    for index, mode in enumerate(("tier1", "tier2", "tier3"), start=1):
        response = _post_attempt(
            client,
            _attempt(f"diagnostic-{index}", mode, f"2026-08-0{index}T00:00:00Z", [
                _response("附近", False, f"item-near-{index}"),
                _response("方便", True, f"item-easy-{index}"),
            ]),
        )
        assert response.status_code == 200, response.text

    review = client.get(f"/api/students/{student['id']}/weak-words")
    assert review.status_code == 200, review.text
    body = review.json()
    assert body["unlocked"] is True
    assert body["completedDiagnosticQuizzes"] == 3
    assert [word["word"] for word in body["words"]] == ["附近"]
    assert body["words"][0]["observationCount"] == 3
    assert body["words"][0]["status"] == "NEEDS_PRACTICE"

    mastery = client.get(f"/api/students/{student['id']}/vocabulary-mastery").json()
    by_word = {word["word"]: word for word in mastery["words"]}
    assert by_word["方便"]["status"] == "STRONG"
    assert by_word["附近"]["correctCount"] == 0


def test_weak_words_wait_for_all_three_diagnostic_rounds(logged_in_student):
    client, student = logged_in_student
    attempt = _attempt("first-diagnostic", "tier1", "2026-08-01T00:00:00Z", [
        _response("附近", False, "item-near-1"),
    ])

    assert _post_attempt(client, attempt).status_code == 200

    review = client.get(
        f"/api/students/{student['id']}/weak-words",
        params={"story_id": "lesson-1", "include_all": "true"},
    )
    assert review.status_code == 200, review.text
    body = review.json()
    assert body["unlocked"] is False
    assert body["completedDiagnosticQuizzes"] == 1
    assert body["words"] == []
    assert body["mastery"][0]["status"] == "PROVISIONAL_REVIEW"


def test_partial_diagnostic_response_updates_weak_words_without_creating_attempt(logged_in_student):
    client, student = logged_in_student
    partial = _attempt("live-diagnostic", "tier1", "2026-08-01T00:00:00Z", [
        {**_response("附近", False, "item-near-live-1"), "quizId": "live-quiz-key"},
    ])
    partial["id"] = "live-quiz-key"

    response = _post_attempt(client, partial, partial=True)
    assert response.status_code == 200, response.text
    assert response.json() == {"acceptedResponses": 1}

    attempts = client.get(
        "/api/vocab-quiz-attempts",
        params={"story_id": "lesson-1", "student_id": student["id"]},
    )
    assert attempts.status_code == 200, attempts.text
    assert attempts.json() == []

    review = client.get(
        f"/api/students/{student['id']}/weak-words",
        params={"story_id": "lesson-1", "include_all": "true"},
    )
    assert review.status_code == 200, review.text
    body = review.json()
    assert body["unlocked"] is False
    assert body["words"] == []
    assert body["mastery"][0]["status"] == "PROVISIONAL_REVIEW"

    completed = {
        **partial,
        "id": "completed-attempt",
        "completedAt": "2026-08-01T00:00:05Z",
    }
    final_response = _post_attempt(client, completed)
    assert final_response.status_code == 200, final_response.text
    mastery = client.get(f"/api/students/{student['id']}/vocabulary-mastery").json()["words"]
    assert next(word for word in mastery if word["word"] == "附近")["observationCount"] == 1


def test_story_weak_words_are_cumulative_across_all_three_rounds(logged_in_student):
    client, student = logged_in_student
    attempts = [
        _attempt("scope-tier-1", "tier1", "2026-08-01T00:00:00Z", [
            _response("第一層弱詞", False, "scope-item-1"),
            _response("第二層弱詞", False, "scope-item-1b"),
            _response("已學會", True, "scope-mastered-1"),
        ]),
        _attempt("scope-tier-2", "tier2", "2026-08-02T00:00:00Z", [
            _response("第一層弱詞", False, "scope-item-2"),
            _response("第二層弱詞", False, "scope-item-2b"),
            _response("已學會", True, "scope-mastered-2"),
        ]),
        _attempt("scope-tier-3", "tier3", "2026-08-03T00:00:00Z", [
            _response("第一層弱詞", False, "scope-item-3"),
            _response("第二層弱詞", False, "scope-item-3b"),
            _response("已學會", True, "scope-mastered-3"),
        ]),
    ]
    for attempt in attempts:
        response = _post_attempt(client, attempt)
        assert response.status_code == 200, response.text

    review = client.get(
        f"/api/students/{student['id']}/weak-words",
        params={"story_id": "teacher-lesson-1-medium", "include_all": "true"},
    )
    assert review.status_code == 200, review.text
    body = review.json()
    assert body["unlocked"] is True
    assert body["completedDiagnosticQuizzes"] == 3
    assert {word["word"] for word in body["words"]} == {"第一層弱詞", "第二層弱詞"}
    assert all(word["word"] != "已學會" for word in body["words"])


def test_medium_and_hard_rounds_update_the_same_word_level_kc(logged_in_student):
    client, student = logged_in_student
    round_data = (
        ("tier1", "easy", "basic_meaning_mcq", "know_it"),
        ("tier2", "medium", "character_to_pinyin_typing", "say_it"),
        ("tier3", "hard", "context_cloze_mcq", "use_it"),
    )
    for index, (mode, level, question_kind, round_type) in enumerate(round_data, start=1):
        result = _response("同一個詞", index == 1, f"same-word-round-{index}", level=level, question_kind=question_kind)
        result.update({"roundType": round_type, "knowledgeDimension": ("meaning", "pinyin_production", "contextual_recall")[index - 1]})
        attempt = _attempt(f"same-word-round-{index}", mode, f"2026-08-0{index}T00:00:00Z", [result])
        attempt["level"] = level
        response = _post_attempt(client, attempt)
        assert response.status_code == 200, response.text

    mastery = client.get(f"/api/students/{student['id']}/vocabulary-mastery").json()
    word = next(row for row in mastery["words"] if row["word"] == "同一個詞")
    assert word["observationCount"] == 3
    assert word["correctCount"] == 1
    assert set(word["seenQuestionTypes"]) == {"basic_meaning_mcq", "character_to_pinyin_typing", "context_cloze_mcq"}
    review = client.get(f"/api/students/{student['id']}/weak-words", params={"story_id": "lesson-1", "include_all": "true"}).json()
    assert review["unlocked"] is True
    assert review["roundPresence"]["tier2"]["level"] == "tier2"


def test_lesson_five_shape_has_fifteen_words_in_each_of_three_rounds(logged_in_student):
    client, student = logged_in_student
    words = [f"課程五詞{i:02d}" for i in range(1, 16)]
    rounds = (
        ("tier1", "easy", "basic_meaning_mcq", "know_it", "meaning"),
        ("tier2", "medium", "character_to_pinyin_typing", "say_it", "pinyin_production"),
        ("tier3", "hard", "context_cloze_mcq", "use_it", "contextual_recall"),
    )
    for index, (mode, level, question_kind, round_type, dimension) in enumerate(rounds, start=1):
        results = []
        for word_index, word in enumerate(words, start=1):
            result = _response(word, word_index % 4 != 0, f"lesson-five-{round_type}-{word_index}", level=level, question_kind=question_kind)
            result.update({
                "roundType": round_type,
                "knowledgeDimension": dimension,
                "quizId": f"lesson-five-{mode}",
            })
            results.append(result)
        attempt = _attempt(f"lesson-five-round-{index}", mode, f"2026-08-1{index}T00:00:00Z", results)
        attempt["level"] = level
        response = _post_attempt(client, attempt)
        assert response.status_code == 200, response.text

    review = client.get(
        f"/api/students/{student['id']}/weak-words",
        params={"story_id": "lesson-1", "include_all": "true"},
    )
    assert review.status_code == 200, review.text
    body = review.json()
    assert body["unlocked"] is True
    assert body["completedDiagnosticQuizzes"] == 3
    assert all(
        body["roundPresence"][mode]["observedWords"] == 15
        and body["roundPresence"][mode]["observations"] == 15
        and body["roundPresence"][mode]["complete"] is True
        for mode in ("tier1", "tier2", "tier3")
    )
    mastery = client.get(f"/api/students/{student['id']}/vocabulary-mastery").json()["words"]
    assert len(mastery) == 15
    assert {word["observationCount"] for word in mastery} == {3}


def test_duplicate_word_exposures_do_not_complete_a_diagnostic_round(logged_in_student):
    client, student = logged_in_student
    duplicate_round = _attempt("duplicate-round", "tier1", "2026-08-04T00:00:00Z", [
        _response("重複詞", False, "duplicate-item-1"),
        _response("重複詞", True, "duplicate-item-2"),
    ])
    assert _post_attempt(client, duplicate_round).status_code == 200

    review = client.get(
        f"/api/students/{student['id']}/weak-words",
        params={"story_id": "lesson-1", "include_all": "true"},
    )
    assert review.status_code == 200, review.text
    body = review.json()
    assert body["unlocked"] is False
    assert body["roundPresence"]["tier1"]["observedWords"] == 1
    assert body["roundPresence"]["tier1"]["observations"] == 2
    assert body["roundPresence"]["tier1"]["complete"] is False


def test_clean_retry_can_complete_a_round_after_an_incomplete_run(logged_in_student):
    client, student = logged_in_student
    incomplete = _attempt("failed-round", "tier1", "2026-08-04T00:00:00Z", [
        _response("詞一", False, "failed-item-1"),
        _response("詞一", True, "failed-item-2"),
    ])
    assert _post_attempt(client, incomplete).status_code == 200

    clean_retry = _attempt("clean-round", "tier1", "2026-08-05T00:00:00Z", [
        _response("詞一", True, "clean-item-1"),
        _response("詞二", True, "clean-item-2"),
    ])
    assert _post_attempt(client, clean_retry).status_code == 200

    review = client.get(
        f"/api/students/{student['id']}/weak-words",
        params={"story_id": "lesson-1", "include_all": "true"},
    )
    assert review.status_code == 200, review.text
    body = review.json()
    assert body["completedDiagnosticQuizzes"] == 1
    assert body["roundPresence"]["tier1"]["complete"] is True


def test_weak_review_is_a_new_bkt_observation_and_attempt_is_immutable(logged_in_student):
    client, student = logged_in_student
    first = _attempt("same-id", "tier1", "2026-08-01T00:00:00Z", [_response("附近", False, "item-1")])
    assert _post_attempt(client, first).status_code == 200

    review = _attempt("review-id", "weak_words", "2026-08-02T00:00:00Z", [_response("附近", True, "item-review", eligible=False)])
    assert _post_attempt(client, review).status_code == 200
    state = client.get(f"/api/students/{student['id']}/vocabulary-mastery").json()["words"]
    assert state[0]["observationCount"] == 2
    assert state[0]["correctCount"] == 1

    changed = {**first, "correctCount": 1, "questionResults": [_response("附近", True, "item-1")]}
    conflict = _post_attempt(client, changed)
    assert conflict.status_code == 409


_E2E_WORD = "e2e-word"
_E2E_ITEMS = {
    "meaning": ("basic_meaning_mcq", "single_choice", "easy", 1, "tier1"),
    "pinyin": ("character_to_pinyin_typing", "free_text", "medium", 2, "tier2"),
    "context": ("context_cloze_mcq", "single_choice", "hard", 3, "tier3"),
}


def _publish_e2e_bank() -> None:
    """One word with a real meaning / pinyin / context item (round-keyed)."""
    items = [
        {
            "questionId": f"{_E2E_WORD}:round{round_number}:v1",
            "wordId": _E2E_WORD,
            "targetWord": _E2E_WORD,
            "level": level,
            "round": round_number,
            "questionType": question_type,
            "answerFormat": answer_format,
            "pinyin": "right",
            "options": ["right", "wrong"] if answer_format == "single_choice" else [],
            "correctAnswer": "right",
            "acceptedAnswers": ["right"],
            "prompt": f"{dimension} for {_E2E_WORD}",
        }
        for dimension, (question_type, answer_format, level, round_number, _mode) in _E2E_ITEMS.items()
    ]
    with db.connect_db() as conn:
        conn.execute(
            "INSERT INTO custom_stories (id, title, frames, published, vocab_assessment) VALUES (%s, %s, %s, TRUE, %s) "
            "ON CONFLICT (id) DO UPDATE SET published = TRUE, vocab_assessment = EXCLUDED.vocab_assessment",
            ("lesson-1", "BKT e2e lesson", Jsonb([]), Jsonb(items)),
        )


def _e2e_payload(attempt_id: str, mode: str, dimension: str, correct: bool, day: str, *, quiz_id: str | None = None) -> dict:
    question_type, _fmt, level, round_number, _tier = _E2E_ITEMS[dimension]
    result = _response(
        _E2E_WORD, correct, f"{_E2E_WORD}:round{round_number}:v1",
        level=level, eligible=mode.startswith("tier"), question_kind=question_type,
    )
    if quiz_id:
        result["quizId"] = quiz_id
    attempt = _attempt(attempt_id, mode, f"{day}T00:00:00Z", [result])
    attempt["level"] = level
    with db.connect_db() as conn:
        version = conn.execute("SELECT vocabulary_version FROM custom_stories WHERE id = 'lesson-1'").fetchone()["vocabulary_version"]
    return {**attempt, "vocabularyVersion": version}


def _post_e2e(client, attempt_id: str, mode: str, dimension: str, correct: bool, day: str):
    response = client.post(
        "/api/vocab-quiz-attempts", params={"today": day},
        json=_e2e_payload(attempt_id, mode, dimension, correct, day),
    )
    assert response.status_code == 200, response.text


def _e2e_word_state(client, student) -> dict:
    words = client.get(f"/api/students/{student['id']}/vocabulary-mastery").json()["words"]
    return next(row for row in words if row["word"] == _E2E_WORD)


def test_unresolved_dimensions_drive_practice_to_strong_and_sm2_enrollment(logged_in_student):
    """meaning wrong, pinyin wrong, context right -> repair meaning, then
    pinyin (never both at once, never a stale historical failure)."""
    client, student = logged_in_student
    _publish_e2e_bank()
    _post_e2e(client, "e2e-d1", "tier1", "meaning", False, "2026-08-01")
    _post_e2e(client, "e2e-d2", "tier2", "pinyin", False, "2026-08-02")
    _post_e2e(client, "e2e-d3", "tier3", "context", True, "2026-08-03")

    state = _e2e_word_state(client, student)
    practice = state["vocabularyState"]["practice"]
    assert practice["unresolvedDimensions"] == ["meaning", "pinyin"]
    assert practice["nextDimension"] == "meaning"
    assert practice["selectionReason"] == "repair_unresolved"
    assert state["vocabularyState"]["review"] == {"status": "NEEDS_PRACTICE", "candidate": True}
    # The historical failed-type list was the stale selector input; it is gone.
    assert "failedQuestionTypes" not in state

    _post_e2e(client, "e2e-p1", "weak_words", "meaning", True, "2026-08-04")
    _post_e2e(client, "e2e-p2", "weak_words", "meaning", True, "2026-08-05")

    state = _e2e_word_state(client, student)
    practice = state["vocabularyState"]["practice"]
    # Meaning is repaired and no longer selected; pinyin is still required even
    # though pooled P(Learned) has crossed the threshold (the original bug: a
    # selector stuck on meaning while completion waited on pinyin).
    assert state["pLearned"] >= 0.95
    assert practice["unresolvedDimensions"] == ["pinyin"]
    assert practice["nextDimension"] == "pinyin"
    assert practice["status"] == "IN_PROGRESS"
    assert state["vocabularyState"]["review"]["status"] == "NEEDS_PRACTICE"
    with db.connect_db() as conn:
        assert conn.execute("SELECT 1 FROM student_vocab_srs WHERE student_id = %s", (student["id"],)).fetchone() is None

    _post_e2e(client, "e2e-p3", "weak_words", "pinyin", True, "2026-08-06")
    _post_e2e(client, "e2e-p4", "weak_words", "pinyin", True, "2026-08-07")

    state = _e2e_word_state(client, student)
    practice = state["vocabularyState"]["practice"]
    assert practice["unresolvedDimensions"] == []
    assert practice["status"] == "COMPLETE"
    assert practice["nextDimension"] is None
    assert state["vocabularyState"]["review"] == {"status": "STRONG", "candidate": False}
    with db.connect_db() as conn:
        scheduled = conn.execute(
            "SELECT reps, interval_days FROM student_vocab_srs WHERE student_id = %s AND word_id = %s",
            (student["id"], _E2E_WORD),
        ).fetchone()
    # STRONG enrolls exactly one SM-2 schedule; corrective answers never advanced it.
    assert scheduled is not None and scheduled["reps"] == 1


def test_due_failure_reopens_repair_without_practice_postponing_sm2(logged_in_student, monkeypatch):
    """Exercise the production API through acquisition, lapse, repair and retention."""
    import routers.vocab_quiz_attempts as attempt_routes

    monkeypatch.setattr(attempt_routes, "settings", replace(
        attempt_routes.settings, app_env="development", srs_day_seconds=86400.0,
    ))
    client, student = logged_in_student
    _publish_e2e_bank()
    for index, dimension in enumerate(("meaning", "pinyin", "context"), start=1):
        _post_e2e(client, f"cycle-d{index}", f"tier{index}", dimension, True, f"2026-10-0{index}")

    def schedule():
        with db.connect_db() as conn:
            return dict(conn.execute(
                "SELECT reps, ease, interval_days, due_on, last_reviewed_on "
                "FROM student_vocab_srs WHERE student_id = %s AND word_id = %s",
                (student["id"], _E2E_WORD),
            ).fetchone())

    def queue(day):
        response = client.get(
            f"/api/students/{student['id']}/review-queue",
            params={"story_id": "lesson-1", "include_all": "true", "today": day},
        )
        assert response.status_code == 200, response.text
        return response.json()["queue"]

    assert _e2e_word_state(client, student)["status"] == "STRONG"
    assert schedule()["due_on"] == datetime(2026, 10, 4, tzinfo=timezone.utc)
    assert queue("2026-10-04")[0]["reviewReason"] == "due"
    _post_e2e(client, "cycle-maintenance-1", "maintenance_review", "context", True, "2026-10-04")
    assert schedule()["reps"] == 2 and schedule()["interval_days"] == 6
    assert schedule()["due_on"] == datetime(2026, 10, 10, tzinfo=timezone.utc)

    # An early response is still BKT evidence but cannot move a due interval.
    before_early = schedule()
    observations = _e2e_word_state(client, student)["observationCount"]
    _post_e2e(client, "cycle-early", "maintenance_review", "pinyin", True, "2026-10-05")
    assert schedule() == before_early
    assert _e2e_word_state(client, student)["observationCount"] == observations + 1

    _post_e2e(client, "cycle-lapse", "maintenance_review", "meaning", False, "2026-10-10")
    lapsed = _e2e_word_state(client, student)
    assert lapsed["status"] == "NEEDS_PRACTICE"
    assert lapsed["vocabularyState"]["practice"]["unresolvedDimensions"] == ["meaning"]
    assert lapsed["vocabularyState"]["practice"]["nextDimension"] == "meaning"
    after_lapse = schedule()
    assert after_lapse["reps"] == 0 and after_lapse["interval_days"] == 1
    assert after_lapse["ease"] < before_early["ease"]
    assert after_lapse["due_on"] == datetime(2026, 10, 11, tzinfo=timezone.utc)
    assert queue("2026-10-10")[0]["reviewReason"] == "weak"

    for index in (1, 2):
        _post_e2e(client, f"cycle-repair-{index}", "weak_words", "meaning", True, "2026-10-10")
        assert schedule() == after_lapse
        if index == 1:
            assert _e2e_word_state(client, student)["status"] == "NEEDS_PRACTICE"
    assert _e2e_word_state(client, student)["status"] == "STRONG"
    assert queue("2026-10-10") == []
    assert queue("2026-10-11")[0]["reviewReason"] == "due"

    # A retry of the old lapse must not reopen the repaired dimension or reset SRS.
    _post_e2e(client, "cycle-lapse", "maintenance_review", "meaning", False, "2026-10-10")
    assert _e2e_word_state(client, student)["status"] == "STRONG"
    assert schedule() == after_lapse
    _post_e2e(client, "cycle-maintenance-2", "maintenance_review", "meaning", True, "2026-10-11")
    assert schedule()["reps"] == 1 and schedule()["interval_days"] == 1
    _post_e2e(client, "cycle-maintenance-3", "maintenance_review", "pinyin", True, "2026-10-12")
    assert schedule()["reps"] == 2 and schedule()["interval_days"] == 6
    assert schedule()["due_on"] == datetime(2026, 10, 18, tzinfo=timezone.utc)
    with db.connect_db() as conn:
        events = conn.execute(
            "SELECT event_type FROM student_vocab_srs_events "
            "WHERE student_id = %s AND word_id = %s ORDER BY id",
            (student["id"], _E2E_WORD),
        ).fetchall()
    assert [event["event_type"] for event in events] == [
        "enrollment", "maintenance_success", "maintenance_failure",
        "maintenance_success", "maintenance_success",
    ]


@pytest.mark.parametrize("dimension", ["meaning", "pinyin", "context"])
def test_interrupted_corrective_streak_cannot_complete_repair_or_enroll_sm2(logged_in_student, dimension):
    client, student = logged_in_student
    _publish_e2e_bank()
    for index, observed in enumerate(("meaning", "pinyin", "context"), start=1):
        _post_e2e(client, f"streak-d{index}", f"tier{index}", observed, observed != dimension, f"2026-10-0{index}")
    for index, (correct, progress) in enumerate(((True, 1), (False, 0), (True, 1)), start=1):
        _post_e2e(client, f"streak-p{index}", "weak_words", dimension, correct, f"2026-10-0{index + 3}")
        state = _e2e_word_state(client, student)
        practice = state["vocabularyState"]["practice"]
        assert practice["unresolvedDimensions"] == [dimension]
        assert practice["repairProgress"] == {dimension: progress}
        assert practice["status"] == "IN_PROGRESS"
        assert state["status"] == "NEEDS_PRACTICE"
        with db.connect_db() as conn:
            assert conn.execute("SELECT 1 FROM student_vocab_srs WHERE student_id = %s", (student["id"],)).fetchone() is None
    _post_e2e(client, "streak-p4", "weak_words", dimension, True, "2026-10-07")
    state = _e2e_word_state(client, student)
    assert state["vocabularyState"]["practice"]["unresolvedDimensions"] == []
    assert state["vocabularyState"]["practice"]["status"] == "COMPLETE"
    assert state["status"] == "STRONG"
    with db.connect_db() as conn:
        assert conn.execute("SELECT count(*) AS n FROM student_vocab_srs WHERE student_id = %s", (student["id"],)).fetchone()["n"] == 1


def test_personalized_practice_requires_two_successes_and_failed_dimension(logged_in_student):
    client, student = logged_in_student
    word = "practice-target"
    for index, (mode, level, question_kind, dimension) in enumerate((
        ("tier1", "easy", "basic_meaning_mcq", "meaning"),
        ("tier2", "medium", "character_to_pinyin_typing", "pinyin_production"),
        ("tier3", "hard", "context_cloze_mcq", "contextual_recall"),
    ), start=1):
        result = _response(word, mode != "tier1", f"practice-diagnostic-{index}", level=level, question_kind=question_kind)
        result.update({"knowledgeDimension": dimension, "quizId": f"practice-diagnostic-{index}"})
        attempt = _attempt(f"practice-diagnostic-{index}", mode, f"2026-08-1{index}T00:00:00Z", [result])
        attempt["level"] = level
        assert _post_attempt(client, attempt, today=f"2026-08-1{index}").status_code == 200

    first_practice = _attempt(
        "practice-corrective-1", "weak_words", "2026-08-20T00:00:00Z",
        [_response(word, True, "practice-corrective-item-1", eligible=False)],
    )
    assert _post_attempt(client, first_practice, today="2026-08-20").status_code == 200
    state = next(row for row in client.get(f"/api/students/{student['id']}/vocabulary-mastery").json()["words"] if row["word"] == word)
    assert state["vocabularyState"]["bkt"]["status"] == "STRONG"
    assert state["vocabularyState"]["review"] == {"status": "NEEDS_PRACTICE", "candidate": True}
    assert state["vocabularyState"]["practice"]["status"] == "IN_PROGRESS"
    assert state["vocabularyState"]["practice"]["repairProgress"] == {"meaning": 1}
    assert state["vocabularyState"]["practice"]["unresolvedDimensions"] == ["meaning"]

    second_practice = _attempt(
        "practice-corrective-2", "weak_words", "2026-08-21T00:00:00Z",
        [_response(word, True, "practice-corrective-item-2", eligible=False)],
    )
    assert _post_attempt(client, second_practice, today="2026-08-21").status_code == 200
    state = next(row for row in client.get(f"/api/students/{student['id']}/vocabulary-mastery").json()["words"] if row["word"] == word)
    assert state["vocabularyState"]["practice"]["status"] == "COMPLETE"
    assert state["vocabularyState"]["practice"]["unresolvedDimensions"] == []
    assert state["vocabularyState"]["practice"]["repairedDimensions"] == ["meaning"]
    assert state["status"] == "STRONG"

    with db.connect_db() as conn:
        scheduled = conn.execute(
            "SELECT reps, interval_days, due_on FROM student_vocab_srs WHERE student_id = %s AND word_id = %s",
            (student["id"], word),
        ).fetchone()
    assert scheduled is not None
    assert scheduled["reps"] == 1
    assert scheduled["interval_days"] == 1

    due = client.get(
        f"/api/students/{student['id']}/review-queue",
        params={"story_id": "lesson-1", "include_all": "true", "today": "2026-08-22"},
    )
    assert due.status_code == 200, due.text
    assert [row["wordId"] for row in due.json()["queue"]] == [word]
    assert due.json()["queue"][0]["reviewReason"] == "due"
    assert next(row for row in due.json()["mastery"] if row["word"] == word)["vocabularyState"]["scheduling"]["status"] == "DUE_FOR_REVIEW"

    maintenance = _attempt(
        "practice-maintenance", "maintenance_review", "2026-08-22T00:00:00Z",
        [_response(word, True, "practice-maintenance-item", eligible=False, question_kind="basic_meaning_mcq")],
    )
    maintenance["questionResults"][0]["quizId"] = "maintenance-round-stable-id"
    partial_maintenance = {**maintenance, "id": "maintenance-partial-id"}
    assert _post_attempt(client, partial_maintenance, partial=True, today="2026-08-22").status_code == 200
    assert _post_attempt(client, maintenance, today="2026-08-22").status_code == 200
    after = client.get(
        f"/api/students/{student['id']}/review-queue",
        params={"story_id": "lesson-1", "include_all": "true", "today": "2026-08-22"},
    )
    assert after.status_code == 200, after.text
    assert after.json()["queue"] == []

    with db.connect_db() as conn:
        events = conn.execute(
            """
            SELECT event_type, correct, quality, old_reps, new_reps,
                   algorithm_version
            FROM student_vocab_srs_events
            WHERE student_id = %s AND word_id = %s
            ORDER BY id
            """,
            (student["id"], word),
        ).fetchall()
    assert [event["event_type"] for event in events] == ["enrollment", "maintenance_success"]
    assert events[0]["correct"] is None and events[0]["quality"] is None
    assert events[1]["correct"] is True and events[1]["quality"] == 4
    assert events[1]["old_reps"] == 1 and events[1]["new_reps"] == 2
    assert all(event["algorithm_version"] == "modified-sm2-v1" for event in events)

    # Retrying the same immutable API attempt must not append another SRS
    # transition, even if the request is persisted twice by the client.
    assert _post_attempt(client, maintenance, today="2026-08-22").status_code == 200
    with db.connect_db() as conn:
        event_count = conn.execute(
            "SELECT COUNT(*) AS count FROM student_vocab_srs_events WHERE student_id = %s AND word_id = %s",
            (student["id"], word),
        ).fetchone()["count"]
    assert event_count == 2

    # The same immutable response must remain a no-op even after the word's
    # next due date. Otherwise a replay after a reconnect could advance the
    # schedule from the current projection a second time.
    assert _post_attempt(client, maintenance, today="2026-08-29").status_code == 200
    with db.connect_db() as conn:
        scheduled = conn.execute(
            "SELECT reps, interval_days, due_on FROM student_vocab_srs WHERE student_id = %s AND word_id = %s",
            (student["id"], word),
        ).fetchone()
        event_count = conn.execute(
            "SELECT COUNT(*) AS count FROM student_vocab_srs_events WHERE student_id = %s AND word_id = %s",
            (student["id"], word),
        ).fetchone()["count"]
    assert scheduled["reps"] == 2
    assert scheduled["interval_days"] == 6
    assert event_count == 2


def test_repeated_exact_item_exposure_counts_only_first_response(logged_in_student):
    client, student = logged_in_student
    first = _response("附近", False, "same-item")
    repeated = _response("附近", True, "same-item")
    assert _post_attempt(
        client,
        _attempt("exposure-1", "tier1", "2026-08-01T00:00:00Z", [first]),
    ).status_code == 200
    # The second attempt repeats the exact item and diagnostic exposure. It is
    # retained as raw audit data but must not become a second BKT observation.
    assert _post_attempt(
        client,
        _attempt("exposure-2", "tier1", "2026-08-02T00:00:00Z", [repeated]),
    ).status_code == 200

    words = client.get(f"/api/students/{student['id']}/vocabulary-mastery").json()["words"]
    assert next(word for word in words if word["word"] == "附近")["observationCount"] == 1


def test_same_word_with_distinct_question_kinds_counts_each_valid_observation(logged_in_student):
    client, student = logged_in_student
    for index, (mode, question_kind) in enumerate(
        (("tier1", "translation"), ("tier2", "reverse"), ("tier3", "listening")),
        start=1,
    ):
        response = _post_attempt(
            client,
            _attempt(
                f"kind-diversity-{index}",
                mode,
                f"2026-08-1{index}T00:00:00Z",
                [_response("多樣題型", index != 2, f"kind-item-{index}", question_kind=question_kind)],
            ),
        )
        assert response.status_code == 200, response.text

    word = next(
        row
        for row in client.get(f"/api/students/{student['id']}/vocabulary-mastery").json()["words"]
        if row["word"] == "多樣題型"
    )
    assert word["observationCount"] == 3
    assert word["correctCount"] == 2
    assert set(word["seenQuestionTypes"]) == {
        "basic_meaning_mcq", "character_to_pinyin_typing", "context_cloze_mcq",
    }


def test_unapproved_diagnostic_response_does_not_enter_bkt_mastery(logged_in_student):
    client, student = logged_in_student
    response = client.post(
        "/api/vocab-quiz-attempts",
        json=_attempt(
            "unapproved-diagnostic",
            "tier1",
            "2026-08-20T00:00:00Z",
            [_response("未核准", False, "unapproved-item", eligible=False)],
        ),
    )
    assert response.status_code == 200, response.text

    mastery = client.get(f"/api/students/{student['id']}/vocabulary-mastery")
    assert mastery.status_code == 200
    assert all(row["word"] != "未核准" for row in mastery.json()["words"])


def test_student_cannot_read_another_students_mastery(logged_in_student):
    client, student = logged_in_student
    with __import__("contextlib").ExitStack() as stack:
        _other_client, other = login_new_client(stack, "Other", "student")
        assert other["id"] != student["id"]
        response = client.get(f"/api/students/{other['id']}/weak-words")
        assert response.status_code == 403


# ── Maintenance is only for words the server currently calls STRONG ─────────

_MAINTENANCE_ENDPOINTS = {
    "completed": "/api/vocab-quiz-attempts",
    "partial": "/api/vocab-quiz-responses",
}


@pytest.fixture
def dev_clock(monkeypatch):
    """Honour ``?today=`` and a real 24h SM-2 day, whatever the ambient APP_ENV."""
    import routers.vocab_quiz_attempts as attempt_routes

    monkeypatch.setattr(attempt_routes, "settings", replace(
        attempt_routes.settings, app_env="development", srs_day_seconds=86400.0,
    ))


def _post_maintenance(client, endpoint, attempt_id, dimension, correct, day, *, quiz_id=None):
    return client.post(
        _MAINTENANCE_ENDPOINTS[endpoint], params={"today": day},
        json=_e2e_payload(attempt_id, "maintenance_review", dimension, correct, day, quiz_id=quiz_id),
    )


def _acquire_strong_scheduled_word(client, student) -> None:
    """Three correct diagnostics: STRONG, enrolled on 10-03 and due on 10-04."""
    _publish_e2e_bank()
    for index, dimension in enumerate(("meaning", "pinyin", "context"), start=1):
        _post_e2e(client, f"guard-d{index}", f"tier{index}", dimension, True, f"2026-10-0{index}")
    assert _e2e_word_state(client, student)["status"] == "STRONG"


def _srs_footprint(student) -> dict:
    """Everything a maintenance write can touch, for an exact before/after check."""
    with db.connect_db() as conn:
        schedule = conn.execute(
            "SELECT * FROM student_vocab_srs WHERE student_id = %s", (student["id"],),
        ).fetchall()
        events = conn.execute(
            "SELECT event_type FROM student_vocab_srs_events WHERE student_id = %s ORDER BY id",
            (student["id"],),
        ).fetchall()
        responses = conn.execute(
            "SELECT COUNT(*) AS n FROM vocab_quiz_responses WHERE student_id = %s", (student["id"],),
        ).fetchone()["n"]
        attempts = conn.execute(
            "SELECT COUNT(*) AS n FROM vocab_quiz_attempts WHERE student_id = %s", (student["id"],),
        ).fetchone()["n"]
    return {
        "schedule": [dict(row) for row in schedule],
        "events": [row["event_type"] for row in events],
        "responses": responses,
        "attempts": attempts,
    }


@pytest.mark.parametrize("endpoint", ["completed", "partial"])
def test_maintenance_is_rejected_for_a_word_that_is_not_strong(logged_in_student, dev_clock, endpoint):
    client, student = logged_in_student
    _acquire_strong_scheduled_word(client, student)
    # A due lapse reopens the meaning repair, so the word leaves STRONG.
    _post_e2e(client, "guard-lapse", "maintenance_review", "meaning", False, "2026-10-04")
    lapsed = _e2e_word_state(client, student)
    assert lapsed["status"] == "NEEDS_PRACTICE"
    before = _srs_footprint(student)

    # The word is due again on 10-05 but is still unrepaired. The UI never
    # offers it, so only a direct API call can get here.
    response = _post_maintenance(client, endpoint, "guard-direct", "pinyin", True, "2026-10-05")

    assert response.status_code == 409, response.text
    assert _srs_footprint(student) == before
    assert _e2e_word_state(client, student)["observationCount"] == lapsed["observationCount"]


@pytest.mark.parametrize("endpoint", ["completed", "partial"])
def test_due_strong_word_answered_wrong_is_accepted_and_reopens_repair(logged_in_student, dev_clock, endpoint):
    client, student = logged_in_student
    _acquire_strong_scheduled_word(client, student)

    # The wrong answer is what takes the word out of STRONG, so the guard has
    # to judge the word as it stood before this write.
    response = _post_maintenance(client, endpoint, "guard-wrong", "meaning", False, "2026-10-04")

    assert response.status_code == 200, response.text
    state = _e2e_word_state(client, student)
    assert state["status"] == "NEEDS_PRACTICE"
    assert state["vocabularyState"]["practice"]["unresolvedDimensions"] == ["meaning"]
    footprint = _srs_footprint(student)
    (schedule,) = footprint["schedule"]
    assert schedule["reps"] == 0 and schedule["interval_days"] == 1
    assert footprint["events"] == ["enrollment", "maintenance_failure"]


@pytest.mark.parametrize("correct", [True, False])
def test_maintenance_partial_save_completion_and_retry_apply_once(logged_in_student, dev_clock, correct):
    client, student = logged_in_student
    _acquire_strong_scheduled_word(client, student)
    answer = ("meaning", correct, "2026-10-04")
    round_id = "guard-round"

    assert _post_maintenance(client, "partial", "guard-partial", *answer, quiz_id=round_id).status_code == 200
    after_partial = _srs_footprint(student)
    observed = _e2e_word_state(client, student)["observationCount"]

    # A wrong answer has already taken the word out of STRONG. Replaying that
    # same response in the completed attempt must not be mistaken for a new
    # maintenance answer on a word that was never STRONG.
    completed = _post_maintenance(client, "completed", "guard-completed", *answer, quiz_id=round_id)
    assert completed.status_code == 200, completed.text
    after_completed = _srs_footprint(student)
    assert after_completed["attempts"] == after_partial["attempts"] + 1
    assert {**after_completed, "attempts": after_partial["attempts"]} == after_partial

    for endpoint, attempt_id in (("completed", "guard-completed"), ("partial", "guard-partial")):
        retry = _post_maintenance(client, endpoint, attempt_id, *answer, quiz_id=round_id)
        assert retry.status_code == 200, retry.text
        assert _srs_footprint(student) == after_completed
    assert _e2e_word_state(client, student)["observationCount"] == observed
    assert after_completed["events"] == [
        "enrollment", "maintenance_success" if correct else "maintenance_failure",
    ]
