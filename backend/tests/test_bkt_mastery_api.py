from conftest import login_new_client
from psycopg.types.json import Jsonb
from types import SimpleNamespace

import db
from routers.vocab_quiz_attempts import _srs_event_results


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
    assert state["vocabularyState"]["practice"]["correctiveSuccesses"] == 1
    assert state["vocabularyState"]["practice"]["failedDimensions"] == ["meaning"]

    second_practice = _attempt(
        "practice-corrective-2", "weak_words", "2026-08-21T00:00:00Z",
        [_response(word, True, "practice-corrective-item-2", eligible=False)],
    )
    assert _post_attempt(client, second_practice, today="2026-08-21").status_code == 200
    state = next(row for row in client.get(f"/api/students/{student['id']}/vocabulary-mastery").json()["words"] if row["word"] == word)
    assert state["vocabularyState"]["practice"]["status"] == "COMPLETE"
    assert state["vocabularyState"]["practice"]["correctiveSuccesses"] == 2
    assert state["vocabularyState"]["practice"]["targetedSuccess"] is True
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
    other_client, other = login_new_client(__import__("contextlib").ExitStack(), "Other", "student")
    assert other["id"] != student["id"]
    response = client.get(f"/api/students/{other['id']}/weak-words")
    assert response.status_code == 403
