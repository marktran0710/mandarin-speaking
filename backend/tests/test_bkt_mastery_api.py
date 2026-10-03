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
            question_type = result.get("questionKind")
            if question_type not in {
                "basic_meaning_mcq", "context_cloze_mcq", "character_to_pinyin_typing",
                "contextual_productive_recall", "productive_recall",
            }:
                question_type = "basic_meaning_mcq" if level == "easy" else "productive_recall"
            answer_format = (
                "free_text" if question_type in {"character_to_pinyin_typing", "contextual_productive_recall", "productive_recall"}
                else "single_choice"
            )
            by_identity[(item_id, level)] = {
                "questionId": item_id,
                "wordId": word,
                "targetWord": word,
                "level": level,
                "questionType": question_type,
                "answerFormat": answer_format,
                "pinyin": "right",
                "options": ["right", "wrong"] if answer_format == "single_choice" else [],
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


def test_all_learned_review_queue_includes_only_lessons_with_three_completed_rounds(logged_in_student):
    client, student = logged_in_student
    for round_number, mode in enumerate(("tier1", "tier2", "tier3"), start=1):
        completed_lesson = _attempt(
            f"global-completed-{round_number}", mode, f"2026-08-0{round_number}T00:00:00Z",
            [_response("global-weak-word", False, f"global-item-{round_number}")],
        )
        completed_lesson["storyId"] = "global-learned-lesson"
        completed_lesson["questionResults"][0]["baseStoryId"] = "global-learned-lesson"
        response = _post_attempt(client, completed_lesson)
        assert response.status_code == 200, response.text

    unfinished = _attempt("global-unfinished", "tier1", "2026-08-04T00:00:00Z", [
        _response("global-not-yet-learned", False, "global-unfinished-item"),
    ])
    unfinished["storyId"] = "global-unfinished-lesson"
    unfinished["questionResults"][0]["baseStoryId"] = "global-unfinished-lesson"
    assert _post_attempt(client, unfinished).status_code == 200

    response = client.get(
        f"/api/students/{student['id']}/review-queue",
        params={"scope": "all_learned", "include_all": "true"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scope"] == "all_learned"
    assert [row["storyId"] for row in body["learnedStories"]] == ["global-learned-lesson"]
    assert {row["wordId"] for row in body["queue"]} == {"global-weak-word"}
    assert body["queue"][0]["reviewReason"] == "weak"


def test_all_learned_scope_rejects_a_single_story_filter(logged_in_student):
    client, student = logged_in_student
    response = client.get(
        f"/api/students/{student['id']}/review-queue",
        params={"scope": "all_learned", "story_id": "lesson-1"},
    )
    assert response.status_code == 422


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


def _start_due_review_session(client, student, day: str):
    response = client.post(
        f"/api/students/{student['id']}/review-sessions", params={"today": day},
    )
    assert response.status_code == 200, response.text
    session = response.json()["session"]
    assert session is not None
    question = session["currentQuestion"]
    assert question["reviewReason"] == "due"
    return session, question


def _answer_server_selected_review(client, student, session, question, day: str, *, correct: bool):
    with db.connect_db() as conn:
        assessment = conn.execute(
            "SELECT vocab_assessment FROM custom_stories WHERE id = %s",
            (question["sourceStoryId"],),
        ).fetchone()["vocab_assessment"]
    item = next(
        value for value in assessment
        if value["questionType"] == question["questionType"]
        and value["targetWord"] == question["word"]
    )
    accepted = item.get("acceptedAnswers") or [item["correctAnswer"]]
    if correct:
        answer = accepted[0]
    elif item.get("answerFormat") == "single_choice":
        answer = next(value for value in item.get("options", []) if value not in accepted)
    else:
        answer = "definitely-not-the-pinyin"
    payload = {"slotId": question["slotId"], "selectedAnswer": answer, "responseTimeMs": 700}
    answer_url = f"/api/students/{student['id']}/review-sessions/{session['sessionId']}/answers"
    response = client.post(answer_url, params={"today": day}, json=payload)
    assert response.status_code == 200, response.text
    return response, answer_url, payload


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
    """Exercise server-selected due activity through acquisition, lapse and retention."""
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
    first_session, first_question = _start_due_review_session(client, student, "2026-10-04")
    assert first_question["dimension"] in {"meaning", "pinyin", "context"}
    _answer_server_selected_review(client, student, first_session, first_question, "2026-10-04", correct=True)
    assert schedule()["reps"] == 2 and schedule()["interval_days"] == 6
    assert schedule()["due_on"] == datetime(2026, 10, 10, tzinfo=timezone.utc)

    # Before the next due date the server creates no maintenance question.
    before_early = schedule()
    observations = _e2e_word_state(client, student)["observationCount"]
    early = client.post(
        f"/api/students/{student['id']}/review-sessions", params={"today": "2026-10-05"},
    )
    assert early.status_code == 200 and early.json()["session"] is None
    assert schedule() == before_early
    assert _e2e_word_state(client, student)["observationCount"] == observations

    lapse_session, lapse_question = _start_due_review_session(client, student, "2026-10-10")
    failed, lapse_url, lapse_payload = _answer_server_selected_review(
        client, student, lapse_session, lapse_question, "2026-10-10", correct=False,
    )
    assert failed.json()["result"]["correct"] is False
    lapsed = _e2e_word_state(client, student)
    assert lapsed["status"] == "NEEDS_PRACTICE"
    assert lapsed["vocabularyState"]["practice"]["unresolvedDimensions"] == [lapse_question["dimension"]]
    assert lapsed["vocabularyState"]["practice"]["nextDimension"] == lapse_question["dimension"]
    after_lapse = schedule()
    assert after_lapse["reps"] == 0 and after_lapse["interval_days"] == 1
    assert after_lapse["ease"] < before_early["ease"]
    assert after_lapse["due_on"] == datetime(2026, 10, 11, tzinfo=timezone.utc)
    assert queue("2026-10-10")[0]["reviewReason"] == "weak"  # next SM-2 due time is tomorrow

    for index in (1, 2):
        _post_e2e(client, f"cycle-repair-{index}", "weak_words", lapse_question["dimension"], True, "2026-10-10")
        assert schedule() == after_lapse
        if index == 1:
            assert _e2e_word_state(client, student)["status"] == "NEEDS_PRACTICE"
    assert _e2e_word_state(client, student)["status"] == "STRONG"
    assert queue("2026-10-10") == []
    assert queue("2026-10-11")[0]["reviewReason"] == "due"

    # A retry of the same server slot returns its saved result and cannot add
    # another BKT observation or SRS event.
    observations_after_lapse = _e2e_word_state(client, student)["observationCount"] - 2
    retried = client.post(lapse_url, params={"today": "2026-10-10"}, json=lapse_payload)
    assert retried.status_code == 200, retried.text
    assert _e2e_word_state(client, student)["status"] == "STRONG"
    assert schedule() == after_lapse
    assert _e2e_word_state(client, student)["observationCount"] == observations_after_lapse + 2

    next_session, next_question = _start_due_review_session(client, student, "2026-10-11")
    _answer_server_selected_review(client, student, next_session, next_question, "2026-10-11", correct=True)
    assert schedule()["reps"] == 1 and schedule()["interval_days"] == 1
    final_session, final_question = _start_due_review_session(client, student, "2026-10-12")
    _answer_server_selected_review(client, student, final_session, final_question, "2026-10-12", correct=True)
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


def test_personalized_repairs_enroll_once_and_due_answer_is_idempotent(logged_in_student, monkeypatch):
    import routers.vocab_quiz_attempts as attempt_routes

    monkeypatch.setattr(attempt_routes, "settings", replace(
        attempt_routes.settings, app_env="development", srs_day_seconds=86400.0,
    ))
    client, student = logged_in_student
    _publish_e2e_bank()
    _post_e2e(client, "practice-d1", "tier1", "meaning", False, "2026-08-01")
    _post_e2e(client, "practice-d2", "tier2", "pinyin", True, "2026-08-02")
    _post_e2e(client, "practice-d3", "tier3", "context", True, "2026-08-03")
    _post_e2e(client, "practice-p1", "weak_words", "meaning", True, "2026-08-20")
    _post_e2e(client, "practice-p2", "weak_words", "meaning", True, "2026-08-21")

    state = _e2e_word_state(client, student)
    assert state["vocabularyState"]["practice"]["status"] == "COMPLETE"
    assert state["status"] == "STRONG"
    with db.connect_db() as conn:
        scheduled = conn.execute(
            "SELECT reps, interval_days, due_on FROM student_vocab_srs WHERE student_id = %s AND word_id = %s",
            (student["id"], _E2E_WORD),
        ).fetchone()
    assert scheduled is not None and scheduled["reps"] == 1 and scheduled["interval_days"] == 1
    assert scheduled["due_on"] == datetime(2026, 8, 22, tzinfo=timezone.utc)

    due_session, question = _start_due_review_session(client, student, "2026-08-22")
    first, answer_url, payload = _answer_server_selected_review(
        client, student, due_session, question, "2026-08-22", correct=True,
    )
    assert first.json()["result"]["correct"] is True
    with db.connect_db() as conn:
        after = dict(conn.execute(
            "SELECT reps, interval_days, due_on FROM student_vocab_srs WHERE student_id = %s AND word_id = %s",
            (student["id"], _E2E_WORD),
        ).fetchone())
        event_count = conn.execute(
            "SELECT COUNT(*) AS count FROM student_vocab_srs_events WHERE student_id = %s AND word_id = %s",
            (student["id"], _E2E_WORD),
        ).fetchone()["count"]
    assert after["reps"] == 2 and after["interval_days"] == 6
    assert after["due_on"] == datetime(2026, 8, 28, tzinfo=timezone.utc)
    assert event_count == 2

    # A retry of the same session slot remains a no-op, including after the
    # schedule has moved on to another due date.
    retry = client.post(answer_url, params={"today": "2026-08-29"}, json=payload)
    assert retry.status_code == 200
    with db.connect_db() as conn:
        final = dict(conn.execute(
            "SELECT reps, interval_days, due_on FROM student_vocab_srs WHERE student_id = %s AND word_id = %s",
            (student["id"], _E2E_WORD),
        ).fetchone())
        final_events = conn.execute(
            "SELECT COUNT(*) AS count FROM student_vocab_srs_events WHERE student_id = %s AND word_id = %s",
            (student["id"], _E2E_WORD),
        ).fetchone()["count"]
    assert final == after
    assert final_events == event_count


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
def test_client_cannot_choose_a_due_maintenance_activity(logged_in_student, dev_clock, endpoint):
    client, student = logged_in_student
    _acquire_strong_scheduled_word(client, student)
    before = _srs_footprint(student)

    # Even an enrolled, due, strong word can only enter through the persisted
    # session slot, which owns activity selection and response identity.
    response = _post_maintenance(client, endpoint, "guard-direct", "pinyin", True, "2026-10-04")

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "SERVER_SELECTED_REVIEW_REQUIRED"
    assert _srs_footprint(student) == before
    assert _e2e_word_state(client, student)["status"] == "STRONG"
