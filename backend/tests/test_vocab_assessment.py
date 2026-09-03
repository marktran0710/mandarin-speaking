from __future__ import annotations

import csv
import io
import json

from vocab_assessment import (
    EXPECTED_QUESTION_COUNT,
    answer_is_accepted,
    build_vocabulary_items,
    normalize_answer,
    parse_vocab_assessment_csv,
    raw_observations_by_word,
    shuffled_options,
    validate_assessment_payload,
    validate_vocab_assessment,
)


WORDS = ["錢包", "在", "哪裡", "聽", "音樂", "有空", "下午茶", "不錯", "咖啡廳", "那裡", "這裡", "冰淇淋", "巧克力", "半", "吧"]


def _questions():
    rows = []
    for index, word in enumerate(WORDS, start=1):
        word_id = f"MC1_{index:03d}"
        for level, weight in (("easy", 1), ("medium", 2), ("hard", 3)):
            is_hard = level == "hard"
            correct_answer = word if level != "easy" else f"meaning {index}"
            accepted = [correct_answer]
            if word_id == "MC1_003" and is_hard:
                accepted.append("哪兒")
            rows.append({
                "word_id": word_id,
                "target_word": word,
                "pinyin": f"word{index}",
                "pos": "N",
                "simple_english_meaning": f"meaning {index}",
                "level": level,
                "difficulty_weight": str(weight),
                "question_type": "productive_recall" if is_hard else ("basic_meaning_mcq" if level == "easy" else "context_cloze_mcq"),
                "answer_format": "free_text" if is_hard else "single_choice",
                "prompt": "請填入____。" if is_hard else "Choose the best answer.",
                "options_json": json.dumps([] if is_hard else [correct_answer, "wrong one", "wrong two", "wrong three"], ensure_ascii=False),
                "correct_answer": correct_answer,
                "accepted_answers_json": json.dumps(accepted, ensure_ascii=False),
                "explanation": "使用繁體中文。",
            })
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    return parse_vocab_assessment_csv(output.getvalue())


def _replace_csv_value(questions, *, question_id, field, value):
    rows = [dict(question.raw) for question in questions]
    for row in rows:
        level = row["level"].strip().upper()
        if f"{row['word_id']}_{level}" == question_id:
            row[field] = value
            break
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    return parse_vocab_assessment_csv(output.getvalue())


def test_parser_builds_the_fixed_three_level_assessment():
    questions = _questions()

    assert len(questions) == EXPECTED_QUESTION_COUNT == 45
    assert validate_vocab_assessment(questions) == []
    assert questions[0].options == ("meaning 1", "wrong one", "wrong two", "wrong three")
    assert questions[0].accepted_answers == ("meaning 1",)
    items = build_vocabulary_items(questions)
    assert len(items) == 15
    assert [question.level for question in items[0].observations] == ["Easy", "Medium", "Hard"]
    assert items[0].observation_for("hard").question_id == "MC1_001_HARD"


def test_ba_has_all_three_question_shapes_and_hard_has_no_options():
    questions = _questions()
    ba = [question for question in questions if question.word_id == "MC1_015"]

    assert [question.question_id for question in ba] == ["MC1_015_EASY", "MC1_015_MEDIUM", "MC1_015_HARD"]
    assert ba[0].answer_format == ba[1].answer_format == "single_choice"
    assert ba[2].answer_format == "free_text"
    assert ba[2].options == ()


def test_alternative_traditional_answers_and_presentation_normalization_are_accepted():
    hard_where = next(question for question in _questions() if question.question_id == "MC1_003_HARD")

    assert answer_is_accepted(hard_where, "哪兒")
    assert answer_is_accepted(hard_where, "  哪裡！ ")
    assert normalize_answer(" 哪 裡？ ") == normalize_answer("哪裡")
    # Answer checking intentionally does not turn Simplified Chinese into Traditional.
    assert not answer_is_accepted(hard_where, "哪里")


def test_mcq_options_and_free_text_rules_are_validated():
    questions = _questions()
    bad_mcq = _replace_csv_value(questions, question_id="MC1_001_EASY", field="options_json", value='["wallet / purse", "school"]')
    bad_hard = _replace_csv_value(questions, question_id="MC1_001_HARD", field="options_json", value='["錢包"]')

    assert "INVALID_MCQ_OPTIONS" in {issue.code for issue in validate_vocab_assessment(bad_mcq)}
    assert "HARD_HAS_OPTIONS" in {issue.code for issue in validate_vocab_assessment(bad_hard)}


def test_question_type_matches_each_assessment_level():
    questions = _replace_csv_value(_questions(), question_id="MC1_001_MEDIUM", field="question_type", value="basic_meaning_mcq")

    assert "INVALID_QUESTION_TYPE" in {issue.code for issue in validate_vocab_assessment(questions)}


def test_simplified_chinese_is_rejected_without_converting_the_source():
    simplified = _replace_csv_value(_questions(), question_id="MC1_001_HARD", field="correct_answer", value="钱包")

    assert "SIMPLIFIED_CHINESE" in {issue.code for issue in validate_vocab_assessment(simplified)}


def test_question_ids_and_option_shuffles_are_deterministic_and_complete():
    question = next(question for question in _questions() if question.question_id == "MC1_007_MEDIUM")

    assert question.question_id == "MC1_007_MEDIUM"
    assert shuffled_options(question, seed="student-7") == shuffled_options(question, seed="student-7")
    assert set(shuffled_options(question, seed="student-7")) == set(question.options)
    assert question.correct_answer in shuffled_options(question, seed="student-7")


def test_raw_observation_helper_preserves_repeated_source_rows():
    questions = _questions()
    repeated = [questions[0], questions[0]]

    raw = raw_observations_by_word(repeated)

    assert len(raw["MC1_001"]) == 2
    assert raw["MC1_001"][0] == raw["MC1_001"][1] == questions[0].raw


def test_api_payload_validation_keeps_the_same_contract_as_csv_import():
    payload = [{
        "questionId": question.question_id,
        "wordId": question.word_id,
        "targetWord": question.target_word,
        "pinyin": question.pinyin,
        "pos": question.part_of_speech,
        "simpleEnglishMeaning": question.simple_english_meaning,
        "level": question.level.casefold(),
        "difficultyWeight": question.difficulty_weight,
        "questionType": question.question_type,
        "answerFormat": question.answer_format,
        "prompt": question.prompt,
        "options": list(question.options),
        "correctAnswer": question.correct_answer,
        "acceptedAnswers": list(question.accepted_answers),
        "explanation": question.explanation,
    } for question in _questions()]

    assert validate_assessment_payload(payload) == []
    payload[1]["questionId"] = "wrong-id"
    assert "INVALID_QUESTION_ID" in {issue.code for issue in validate_assessment_payload(payload)}
    payload[1]["questionId"] = "MC1_001_MEDIUM"
    payload[1]["options"] = ["valid", 123]
    assert "PAYLOAD_OPTIONS_INVALID" in {issue.code for issue in validate_assessment_payload(payload)}
