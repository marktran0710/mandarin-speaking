from analytics.learner_model.bkt.question_validation import (
    audit_production_bkt_assessments,
    validate_production_bkt_assessment,
)


def _assessment():
    return [
        {
            "questionId": "Q0001",
            "wordId": "word-1",
            "round": 1,
            "tier": "tier1",
            "questionType": "basic_meaning_mcq",
            "answerFormat": "single_choice",
        },
        {
            "questionId": "Q0002",
            "wordId": "word-1",
            "round": 2,
            "tier": "tier2",
            "questionType": "character_to_pinyin_typing",
            "answerFormat": "free_text",
        },
        {
            "questionId": "Q0003",
            "wordId": "word-1",
            "round": 3,
            "tier": "tier3",
            "questionType": "context_cloze_mcq",
            "answerFormat": "single_choice",
        },
    ]


def _error_codes(report):
    return {error["code"] for error in report["errors"]}


def test_production_assessment_accepts_the_exact_three_round_contract():
    report = validate_production_bkt_assessment(_assessment(), story_id="lesson-1")

    assert report["valid"] is True
    assert report["itemsChecked"] == 3
    assert report["wordsChecked"] == 1
    assert report["errors"] == []


def test_production_assessment_rejects_missing_round():
    report = validate_production_bkt_assessment(_assessment()[:2], story_id="lesson-1")

    assert report["valid"] is False
    assert "PRODUCTION_MISSING_ROUND" in _error_codes(report)


def test_production_assessment_rejects_wrong_question_type_and_format():
    assessment = _assessment()
    assessment[1]["questionType"] = "context_cloze_mcq"
    assessment[1]["answerFormat"] = "single_choice"

    report = validate_production_bkt_assessment(assessment)

    assert "PRODUCTION_WRONG_QUESTION_TYPE" in _error_codes(report)
    assert "PRODUCTION_WRONG_ANSWER_FORMAT" in _error_codes(report)


def test_production_assessment_rejects_unsupported_and_duplicate_items():
    assessment = _assessment()
    assessment.append({
        "questionId": "Q0002-DUPLICATE",
        "wordId": "word-1",
        "round": 2,
        "tier": "tier2",
        "questionType": "unsupported_review_type",
        "answerFormat": "single_choice",
    })

    report = validate_production_bkt_assessment(assessment)

    assert "PRODUCTION_DUPLICATE_WORD_ROUND" in _error_codes(report)
    assert "PRODUCTION_UNSUPPORTED_QUESTION_TYPE" in _error_codes(report)


def test_production_assessment_rejects_unapproved_items():
    assessment = _assessment()
    assessment[0]["validationStatus"] = "DRAFT"

    report = validate_production_bkt_assessment(assessment)

    assert "PRODUCTION_UNAPPROVED_ITEM" in _error_codes(report)


def test_production_audit_aggregates_published_stories():
    report = audit_production_bkt_assessments([
        {"id": "lesson-good", "vocab_assessment": _assessment()},
        {"id": "lesson-bad", "vocab_assessment": _assessment()[:1]},
    ])

    assert report["mode"] == "production-vocab-assessment"
    assert report["valid"] is False
    assert report["summary"] == {
        "storiesChecked": 2,
        "storiesPassed": 1,
        "storiesFailed": 1,
        "itemsChecked": 4,
        "wordsChecked": 2,
    }


def test_production_audit_does_not_treat_empty_scope_as_valid():
    report = audit_production_bkt_assessments([])

    assert report["valid"] is False
    assert report["summary"]["storiesChecked"] == 0
