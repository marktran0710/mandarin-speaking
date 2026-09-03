from conftest import login_new_client


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
        response = client.post(
            "/api/vocab-quiz-attempts",
            json=_attempt(f"diagnostic-{index}", mode, f"2026-08-0{index}T00:00:00Z", [
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
    assert body["words"][0]["status"] == "NEEDS_REVIEW"

    mastery = client.get(f"/api/students/{student['id']}/vocabulary-mastery").json()
    by_word = {word["word"]: word for word in mastery["words"]}
    assert by_word["方便"]["status"] == "MASTERED"
    assert by_word["附近"]["correctCount"] == 0


def test_weak_words_wait_for_all_three_diagnostic_rounds(logged_in_student):
    client, student = logged_in_student
    attempt = _attempt("first-diagnostic", "tier1", "2026-08-01T00:00:00Z", [
        _response("附近", False, "item-near-1"),
    ])

    assert client.post("/api/vocab-quiz-attempts", json=attempt).status_code == 200

    review = client.get(
        f"/api/students/{student['id']}/weak-words",
        params={"story_id": "lesson-1", "include_all": "true"},
    )
    assert review.status_code == 200, review.text
    body = review.json()
    assert body["unlocked"] is False
    assert body["completedDiagnosticQuizzes"] == 1
    assert body["words"] == []
    assert body["mastery"][0]["status"] == "UNASSESSED"


def test_partial_diagnostic_response_updates_weak_words_without_creating_attempt(logged_in_student):
    client, student = logged_in_student
    partial = _attempt("live-diagnostic", "tier1", "2026-08-01T00:00:00Z", [
        {**_response("附近", False, "item-near-live-1"), "quizId": "live-quiz-key"},
    ])
    partial["id"] = "live-quiz-key"

    response = client.post("/api/vocab-quiz-responses", json=partial)
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
    assert body["mastery"][0]["status"] == "UNASSESSED"

    completed = {
        **partial,
        "id": "completed-attempt",
        "completedAt": "2026-08-01T00:00:05Z",
    }
    final_response = client.post("/api/vocab-quiz-attempts", json=completed)
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
        response = client.post("/api/vocab-quiz-attempts", json=attempt)
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
        ("tier3", "hard", "contextual_productive_recall", "use_it"),
    )
    for index, (mode, level, question_kind, round_type) in enumerate(round_data, start=1):
        result = _response("同一個詞", index == 1, f"same-word-round-{index}", level=level, question_kind=question_kind)
        result.update({"roundType": round_type, "knowledgeDimension": ("meaning", "pinyin_production", "contextual_recall")[index - 1]})
        attempt = _attempt(f"same-word-round-{index}", mode, f"2026-08-0{index}T00:00:00Z", [result])
        attempt["level"] = level
        response = client.post("/api/vocab-quiz-attempts", json=attempt)
        assert response.status_code == 200, response.text

    mastery = client.get(f"/api/students/{student['id']}/vocabulary-mastery").json()
    word = next(row for row in mastery["words"] if row["word"] == "同一個詞")
    assert word["observationCount"] == 3
    assert word["correctCount"] == 1
    assert set(word["seenQuestionTypes"]) == {"basic_meaning_mcq", "character_to_pinyin_typing", "contextual_productive_recall"}
    review = client.get(f"/api/students/{student['id']}/weak-words", params={"story_id": "lesson-1", "include_all": "true"}).json()
    assert review["unlocked"] is True
    assert review["roundPresence"]["tier2"]["level"] == "medium"


def test_lesson_five_shape_has_fifteen_words_in_each_of_three_rounds(logged_in_student):
    client, student = logged_in_student
    words = [f"課程五詞{i:02d}" for i in range(1, 16)]
    rounds = (
        ("tier1", "easy", "basic_meaning_mcq", "know_it", "meaning"),
        ("tier2", "medium", "character_to_pinyin_typing", "say_it", "pinyin_production"),
        ("tier3", "hard", "contextual_productive_recall", "use_it", "contextual_recall"),
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
        response = client.post("/api/vocab-quiz-attempts", json=attempt)
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
    assert client.post("/api/vocab-quiz-attempts", json=duplicate_round).status_code == 200

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
    assert client.post("/api/vocab-quiz-attempts", json=incomplete).status_code == 200

    clean_retry = _attempt("clean-round", "tier1", "2026-08-05T00:00:00Z", [
        _response("詞一", True, "clean-item-1"),
        _response("詞二", True, "clean-item-2"),
    ])
    assert client.post("/api/vocab-quiz-attempts", json=clean_retry).status_code == 200

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
    assert client.post("/api/vocab-quiz-attempts", json=first).status_code == 200

    review = _attempt("review-id", "weak_words", "2026-08-02T00:00:00Z", [_response("附近", True, "item-review", eligible=False)])
    assert client.post("/api/vocab-quiz-attempts", json=review).status_code == 200
    state = client.get(f"/api/students/{student['id']}/vocabulary-mastery").json()["words"]
    assert state[0]["observationCount"] == 2
    assert state[0]["correctCount"] == 1

    changed = {**first, "correctCount": 1, "questionResults": [_response("附近", True, "item-1")]}
    conflict = client.post("/api/vocab-quiz-attempts", json=changed)
    assert conflict.status_code == 409


def test_repeated_exact_item_exposure_counts_only_first_response(logged_in_student):
    client, student = logged_in_student
    first = _response("附近", False, "same-item")
    repeated = _response("附近", True, "same-item")
    assert client.post(
        "/api/vocab-quiz-attempts",
        json=_attempt("exposure-1", "tier1", "2026-08-01T00:00:00Z", [first]),
    ).status_code == 200
    # The second attempt repeats the exact item and diagnostic exposure. It is
    # retained as raw audit data but must not become a second BKT observation.
    assert client.post(
        "/api/vocab-quiz-attempts",
        json=_attempt("exposure-2", "tier2", "2026-08-02T00:00:00Z", [repeated]),
    ).status_code == 200

    words = client.get(f"/api/students/{student['id']}/vocabulary-mastery").json()["words"]
    assert next(word for word in words if word["word"] == "附近")["observationCount"] == 1


def test_same_word_with_distinct_question_kinds_counts_each_valid_observation(logged_in_student):
    client, student = logged_in_student
    for index, (mode, question_kind) in enumerate(
        (("tier1", "translation"), ("tier2", "reverse"), ("tier3", "listening")),
        start=1,
    ):
        response = client.post(
            "/api/vocab-quiz-attempts",
            json=_attempt(
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
    assert set(word["seenQuestionTypes"]) == {"translation", "reverse", "listening"}


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
