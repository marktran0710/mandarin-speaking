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


def test_l5_2_vocabulary_list_bank_has_every_supplied_word_and_coverage():
    questions = _bank("l5-2-vocab-assessment.csv")

    assert len(questions) == 78
    metadata = {
        question.target_word: (question.pinyin, question.part_of_speech, question.simple_english_meaning)
        for question in questions
    }
    assert metadata == {
        "\u8ddf": ("g\u0113n", "Conj", "and"), "\u53ef\u662f": ("k\u011bsh\u00ec", "Conj", "but"),
        "\u623f\u9593": ("f\u00e1ngji\u0101n", "N", "room"), "\u623f\u5b50": ("f\u00e1ngzi", "N", "building; house"),
        "\u68df": ("d\u00f2ng", "M", "measure word for buildings"), "\u88e1": ("l\u01d0", "N", "inside; in"),
        "\u5916": ("w\u00e0i", "N", "outside"), "\u5ba2\u5ef3": ("k\u00e8t\u012bng", "N", "living room"),
        "\u684c\u5b50": ("zhu\u014dzi", "N", "table"), "\u6905\u5b50": ("y\u01d0zi", "N", "chair"),
        "\u5f35": ("zh\u0101ng", "M", "measure word for tables and chairs"), "\u4e0a\u9762": ("sh\u00e0ngmi\u00e0n", "N", "above; over; on top of; on the surface of"),
        "\u6709": ("y\u01d2u", "Vst", "there is/are; to exist"), "\u54e5\u54e5": ("g\u0113ge", "N", "elder brother"),
        "\u59d0\u59d0": ("ji\u011bjie", "N", "elder sister"), "\u5f1f\u5f1f": ("d\u00ecdi", "N", "younger brother"),
        "\u59b9\u59b9": ("m\u00e8imei", "N", "younger sister"), "\u6c99\u767c": ("sh\u0101f\u0101", "N", "sofa"),
        "\u4e0b\u9762": ("xi\u00e0mi\u00e0n", "N", "below; under; underneath"), "\u65c1\u908a": ("p\u00e1ngbi\u0101n", "N", "side; by the side of; next to"),
        "\u524d": ("qi\u00e1n", "N", "the front; the front side; ahead; in front"), "\u5f8c": ("h\u00f2u", "N", "at the back; behind"),
        "\u5e6b": ("b\u0101ng", "V", "to help"), "\u627e": ("zh\u01ceo", "V", "to look for"),
        "\u5eda\u623f": ("ch\u00faf\u00e1ng", "N", "kitchen"), "\u518d": ("z\u00e0i", "Adv", "again"),
    }
    li_hard = next(question for question in questions if question.question_id == "L5_2_021_HARD")
    assert set(li_hard.accepted_answers) == {"\u88e1", "\u88e1\u9762"}
    sister_hard = next(question for question in questions if question.question_id == "L5_2_025_HARD")
    assert set(sister_hard.accepted_answers) == {"\u59d0\u59d0", "\u59ca\u59ca"}
    prompts_and_explanations = "\n".join(question.prompt + question.explanation for question in questions)
    assert "\u9019\u500b\u86cb\u7cd5\u8ddf\u9019\u74f6\u679c\u6c41\u4e00\u5171\u591a\u5c11\u9322\uff1f" in prompts_and_explanations
    assert "\u6211\u5bb6\u7684\u5eda\u623f\u5f88\u5927\uff0c\u6211\u5e38\u5e38\u5728\u5bb6\u505a\u98ef\u3002" in prompts_and_explanations

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
    tv_questions = [q for q in questions if q.target_word == "\u96fb\u8996\u6a5f" and q.level in {"Medium", "Hard"}]
    assert all(set(q.accepted_answers) == {"\u96fb\u8996\u6a5f", "\u96fb\u8996"} for q in tv_questions)
    sun_questions = [q for q in questions if q.target_word == "\u66ec\u592a\u967d" and q.level in {"Medium", "Hard"}]
    assert all(set(q.accepted_answers) == {"\u66ec\u592a\u967d", "\u6652\u592a\u967d"} for q in sun_questions)


def test_lesson5_banks_do_not_duplicate_question_ids_or_prompts_across_parts():
    questions = []
    for filename in ("l5-2-vocab-assessment.csv", "l5-3-vocab-assessment.csv"):
        questions.extend(parse_vocab_assessment_csv(BANK_DIRECTORY / filename))

    question_ids = [question.question_id for question in questions]
    prompts = [normalize_answer(question.prompt) for question in questions]
    assert len(question_ids) == len(set(question_ids)) == 111
    assert len(prompts) == len(set(prompts))
