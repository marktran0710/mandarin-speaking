from __future__ import annotations

from collections import Counter

from scripts.import_question_bank_workbook import build_payloads, read_rows, validate_source_rows


def test_exported_workbook_question_bank_is_complete_and_internally_consistent():
    rows = read_rows()

    assert len(rows) == 648
    assert validate_source_rows(rows) == []
    assert Counter(row["Section"] for row in rows) == Counter({
        "5-1": 45, "5-2": 78, "5-3": 33,
        "6-1": 60, "6-2": 66, "6-3": 45,
        "7-1": 75, "7-2": 48, "7-3": 36,
        "8-1": 72, "8-2": 69, "8-3": 21,
    })


def test_workbook_rounds_map_to_runtime_question_contract():
    payloads = build_payloads(read_rows())

    assert sum(len(payload) for payload in payloads.values()) == 648
    sample = payloads["5-2"]
    assert [(question["level"], question["questionType"], question["answerFormat"]) for question in sample[:3]] == [
        ("easy", "basic_meaning_mcq", "single_choice"),
        ("medium", "character_to_pinyin_typing", "free_text"),
        ("hard", "context_cloze_mcq", "single_choice"),
    ]
    tv = [question for question in payloads["5-3"] if question["wordId"] == "C5-5-3-I2-W044"]
    assert all(question["targetWord"] == "電視(機)" for question in tv)
    assert tv[1]["acceptedAnswers"] == [
        "diànshì(jī)", "dian4shi4(ji1)", "dian4 shi4(ji1)",
        "diànshìjī", "dian4shi4ji1", "dian4 shi4 ji1", "diànshì", "dian4shi4", "dian4 shi4",
    ]
