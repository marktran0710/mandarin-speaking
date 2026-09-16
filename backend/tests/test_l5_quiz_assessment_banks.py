from __future__ import annotations

from collections import Counter
from pathlib import Path

from vocab_assessment import normalize_answer, parse_vocab_assessment_csv, validate_vocab_assessment


BANK_DIRECTORY = Path(__file__).parents[1] / "scripts" / "data" / "quiz_assessments"


def _bank(filename: str):
    questions = parse_vocab_assessment_csv(BANK_DIRECTORY / filename)
    assert validate_vocab_assessment(questions) == []
    normalized_prompts = [normalize_answer(question.prompt) for question in questions]
    assert not [prompt for prompt, count in Counter(normalized_prompts).items() if count > 1]
    return questions


def test_l5_2_dialogue_bank_has_every_referenced_word_and_dialogue_coverage():
    questions = _bank("l5-2-vocab-assessment.csv")

    assert len(questions) == 48
    assert {question.target_word for question in questions} == {
        "有", "媽", "房間", "客廳", "桌子", "哥哥", "沙發", "下面",
        "上面", "旁邊", "幫", "好嗎", "忙", "廚房", "做飯", "書",
    }
    metadata = {
        question.target_word: (question.pinyin, question.part_of_speech, question.simple_english_meaning)
        for question in questions
    }
    assert metadata["\u6709"] == ("y\u01d2u", "Vst", "there is/are; to exist")
    you_easy = next(question for question in questions if question.question_id == "L5_2_001_EASY")
    assert you_easy.explanation == "\u300c\u6709\u300d means there is/are; to exist in this sentence."
    assert metadata["\u5fd9"] == ("m\u00e1ng", "Vs", "busy")
    assert metadata["\u505a\u98ef"] == ("zu\u00f2f\u00e0n", "V", "to cook")
    prompts_and_explanations = "\n".join(question.prompt + question.explanation for question in questions)
    assert "客廳的桌子上有一個錢包" in prompts_and_explanations
    assert "沙發上面、下面跟旁邊都沒有" in prompts_and_explanations
    assert "錢包在我的書下面" in prompts_and_explanations


def test_l5_3_reading_bank_has_every_referenced_word_and_reading_coverage():
    questions = _bank("l5-3-vocab-assessment.csv")

    assert len(questions) == 33
    assert {question.target_word for question in questions} == {
        "床", "電視機", "新的", "看電視", "中文", "英文", "窗戶", "大", "貓", "喜歡", "曬太陽",
    }
    metadata = {
        question.target_word: (question.pinyin, question.part_of_speech, question.simple_english_meaning)
        for question in questions
    }
    assert metadata["\u4e2d\u6587"][0] == "zh\u014dngw\u00e9n"
    assert metadata["\u82f1\u6587"][0] == "y\u012bngw\u00e9n"
    assert metadata["\u7a97\u6236"][0] == "chu\u0101ngh\u00f9"
    prompts_and_explanations = "\n".join(question.prompt + question.explanation for question in questions)
    assert "我的房間裡有一張桌子、一張床跟一張沙發" in prompts_and_explanations
    assert "有中文書，也有英文書" in prompts_and_explanations
    assert "我的貓喜歡在窗戶旁邊曬太陽" in prompts_and_explanations


def test_lesson5_banks_do_not_duplicate_question_ids_or_prompts_across_parts():
    questions = []
    for filename in ("l5-2-vocab-assessment.csv", "l5-3-vocab-assessment.csv"):
        questions.extend(parse_vocab_assessment_csv(BANK_DIRECTORY / filename))

    question_ids = [question.question_id for question in questions]
    prompts = [normalize_answer(question.prompt) for question in questions]
    assert len(question_ids) == len(set(question_ids)) == 81
    assert len(prompts) == len(set(prompts))
