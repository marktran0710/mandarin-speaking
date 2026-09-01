from analytics.bkt_question_validation import (
    classify_bkt_response,
    validate_bkt_diagnostic_design,
    validate_vocabulary_question,
)
from analytics.knowledge_tracing import normalize_vocab_attempts


def question(**over):
    value = {
        "question_id": "q1",
        "story_id": "lesson-1",
        "level": "easy",
        "word_id": "餐廳",
        "question_type": "translation",
        "prompt": "餐廳",
        "correct_answer": "restaurant",
        "options": ["restaurant", "hospital", "library", "school"],
        "validation_status": "APPROVED",
    }
    value.update(over)
    return value


def test_valid_approved_lexical_item_is_bkt_eligible():
    result = validate_vocabulary_question(question())
    assert result.valid_for_quiz is True
    assert result.eligible_for_bkt is True
    assert result.errors == []


def test_missing_or_multiple_targets_are_blocked():
    assert "MISSING_TARGET_WORD" in {
        issue["code"] for issue in validate_vocabulary_question(question(word_id=None, word=None)).errors
    }
    assert "MULTIPLE_TARGET_KCS" in {
        issue["code"] for issue in validate_vocabulary_question(question(target_word_ids=["餐廳", "附近"])).errors
    }


def test_duplicate_options_and_unapproved_items_are_blocked():
    result = validate_vocabulary_question(question(options=["restaurant", "Restaurant", "school", "library"], validation_status="DRAFT"))
    codes = {issue["code"] for issue in result.errors}
    assert {"DUPLICATE_OPTIONS", "UNAPPROVED_RESEARCH_ITEM"} <= codes
    assert result.eligible_for_bkt is False


def test_three_distinct_diagnostic_quizzes_pass_and_type_diversity_warns_only():
    questions = [
        question(question_id="q1", mode="tier1", question_type="translation"),
        question(question_id="q2", mode="tier2", question_type="translation"),
        question(question_id="q3", mode="tier3", question_type="translation"),
    ]
    report = validate_bkt_diagnostic_design(questions)
    row = report["words"][0]
    assert row["coverage_status"] == "PASS"
    assert row["distinct_item_count"] == 3
    assert row["bkt_eligible_observation_count"] == 3
    assert row["type_diversity_warning"] == "INSUFFICIENT_TYPE_DIVERSITY"


def test_reused_item_and_missing_quiz_slot_do_not_count_as_three_observations():
    questions = [
        question(question_id="same", mode="tier1"),
        question(question_id="same", mode="tier2"),
        question(question_id="same", mode="tier3"),
    ]
    row = validate_bkt_diagnostic_design(questions)["words"][0]
    assert row["coverage_status"] == "DUPLICATE_ITEM"
    assert row["distinct_item_count"] == 1


def test_one_invalid_item_leaves_insufficient_valid_evidence():
    questions = [
        question(question_id="q1", mode="tier1"),
        question(question_id="q2", mode="tier2", options=["restaurant", "restaurant", "school"]),
        question(question_id="q3", mode="tier3"),
    ]
    row = validate_bkt_diagnostic_design(questions)["words"][0]
    assert row["coverage_status"] == "INVALID_ITEM"
    assert row["bkt_eligible_observation_count"] == 2


def test_runtime_response_requires_explicit_server_approved_gate():
    response = {
        "word": "餐廳",
        "conceptId": "餐廳",
        "itemId": "item-1",
        "questionKind": "translation",
        "level": "easy",
        "isBktEligible": True,
        "bktValidationStatus": "APPROVED",
        "diagnosticExposureId": "lesson-1:easy:tier1:item-1",
        "correct": True,
    }
    assert classify_bkt_response(response, {"mode": "tier1"}) == (True, [])
    assert classify_bkt_response({**response, "assistedResponse": True}, {"mode": "tier1"})[0] is False
    assert classify_bkt_response({**response, "isBktEligible": False}, {"mode": "tier1"})[0] is False


def test_strict_normalization_uses_first_response_per_item_and_diagnostic_exposure():
    base = {
        "word": "餐廳", "conceptId": "餐廳", "itemId": "item-1",
        "questionKind": "translation", "level": "easy",
        "isBktEligible": True, "bktValidationStatus": "APPROVED",
        "diagnosticExposureId": "lesson-1:easy:tier1:item-1",
    }
    normalized = normalize_vocab_attempts([
        {"id": "first", "studentId": "s1", "completedAt": "2026-01-01T00:00:00Z", "mode": "tier1", "questionResults": [{**base, "correct": False}]},
        {"id": "retry", "studentId": "s1", "completedAt": "2026-01-02T00:00:00Z", "mode": "tier1", "questionResults": [{**base, "correct": True}]},
    ], eligible_only=True, deduplicate_diagnostic_exposures=True)
    assert len(normalized.records) == 1
    assert normalized.records[0].correct is False
    assert normalized.counters["duplicate_diagnostic_responses"] == 1
