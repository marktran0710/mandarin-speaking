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


def test_l5_3_vocabulary_bank_has_every_referenced_word_and_vocab_coverage():
    questions = _bank("l5-3-vocab-assessment.csv")

    assert len(questions) == 33
    assert {question.target_word for question in questions} == {
        "\u5e8a", "\u5bb6\u5177", "\u96fb\u8996\u6a5f", "\u7a97\u6236", "\u9580", "\u8c93",
        "\u72d7", "\u9ce5", "\u96bb", "\u66ec\u592a\u967d", "\u592a\u967d",
    }
    metadata = {
        question.target_word: (question.pinyin, question.part_of_speech, question.simple_english_meaning)
        for question in questions
    }
    assert metadata == {
        "\u5e8a": ("chu\u00e1ng", "N", "bed"),
        "\u5bb6\u5177": ("ji\u0101j\u00f9", "N", "furniture"),
        "\u96fb\u8996\u6a5f": ("di\u00e0nsh\u00ecj\u012b", "N", "TV (television)"),
        "\u7a97\u6236": ("chu\u0101ngh\u00f9", "N", "window"),
        "\u9580": ("m\u00e9n", "N", "door"),
        "\u8c93": ("m\u0101o", "N", "cat"),
        "\u72d7": ("g\u01d2u", "N", "dog"),
        "\u9ce5": ("ni\u01ceo", "N", "bird"),
        "\u96bb": ("zh\u012b", "M", "measure word for animals"),
        "\u66ec\u592a\u967d": ("sh\u00e0i t\u00e0iy\u00e1ng", "phrase", "to bask in the sun"),
        "\u592a\u967d": ("t\u00e0iy\u00e1ng", "N", "the sun"),
    }
    assert all(
        question.correct_answer == (question.simple_english_meaning if question.level == "Easy" else question.target_word)
        for question in questions
    )
    prompts_and_explanations = "\n".join(question.prompt + question.explanation for question in questions)
    assert "\u54e5\u54e5\u559c\u6b61\u5728\u5e8a\u4e0a\u770b\u66f8" in prompts_and_explanations
    assert "\u9019\u500b\u65b0\u623f\u5b50\u6c92\u6709\u5f88\u591a\u5bb6\u5177" in prompts_and_explanations
    assert "\u6211\u5bb6\u6709\u4e00\u96bb\u8c93\u3001\u5169\u96bb\u72d7\u548c\u4e09\u96bb\u9ce5" in prompts_and_explanations
    assert "\u6211\u7684\u8c93\u5728\u623f\u5b50\u5916\u9762\u66ec\u592a\u967d" in prompts_and_explanations


def test_lesson5_banks_do_not_duplicate_question_ids_or_prompts_across_parts():
    questions = []
    for filename in ("l5-2-vocab-assessment.csv", "l5-3-vocab-assessment.csv"):
        questions.extend(parse_vocab_assessment_csv(BANK_DIRECTORY / filename))

    question_ids = [question.question_id for question in questions]
    prompts = [normalize_answer(question.prompt) for question in questions]
    assert len(question_ids) == len(set(question_ids)) == 81
    assert len(prompts) == len(set(prompts))
