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


def test_story_weak_words_are_cumulative_across_all_easy_quiz_tiers(logged_in_student):
    client, student = logged_in_student
    attempts = [
        _attempt("scope-tier-1", "tier1", "2026-08-01T00:00:00Z", [
            _response("第一層弱詞", False, "scope-item-1"),
            _response("已學會", True, "scope-mastered-1"),
        ]),
        _attempt("scope-tier-2", "tier2", "2026-08-02T00:00:00Z", [
            _response("第二層弱詞", False, "scope-item-2"),
            _response("已學會", True, "scope-mastered-2"),
        ]),
        _attempt("scope-tier-3", "tier3", "2026-08-03T00:00:00Z", [
            _response("第一層弱詞", True, "scope-item-3"),
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
