from scripts.export_quiz_questions import ALL_TIERS, build_question_rows


def test_cloze_export_keeps_context_sentence_as_a_single_blank_prompt():
    story = {
        "id": "story-1",
        "title": "Test story",
        "published": True,
        "frames": [{
            "vocabulary": "貓",
            "vocabularyTranslation": "cat",
            "vocabularyPinyin": "māo",
            "vocabularyPos": "N",
            "vocabularyCloze": '[[{"sentence":"我有一隻貓。","distractors":["狗"]}]]',
        }],
    }

    rows = build_question_rows([story], tiers=ALL_TIERS)

    cloze_rows = [row for row in rows if row["question_type"] == "cloze"]
    assert len(cloze_rows) == 3
    assert {row["prompt"] for row in cloze_rows} == {"我有一隻____。"}
    assert {row["context_sentence"] for row in cloze_rows} == {"我有一隻____。"}
