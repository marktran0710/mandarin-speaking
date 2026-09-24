from scripts.export_quiz_questions import ALL_TIERS, build_question_rows


def _question(level: str, question_type: str, prompt: str, answer: str, options: list[str]) -> dict:
    return {
        "questionId": f"word-{level}",
        "wordId": "word-1",
        "targetWord": "學習",
        "pinyin": "xue2xi2",
        "pos": "V",
        "simpleEnglishMeaning": "to learn",
        "level": level,
        "questionType": question_type,
        "prompt": prompt,
        "options": options,
        "correctAnswer": answer,
        "acceptedAnswers": [answer],
    }


def test_export_reads_only_canonical_assessment_rows():
    story = {
        "id": "story-1",
        "title": "Canonical story",
        "published": True,
        "lesson_number": 5,
        "lesson_sub_order": 1,
        "frames": [{"vocabularyDistractors": "should not be read"}],
        "vocab_assessment": [
            _question("easy", "basic_meaning_mcq", "What does 學習 mean?", "to learn", ["to learn", "to eat"]),
            _question("medium", "character_to_pinyin_typing", "Type the pinyin.", "xue2xi2", []),
            _question("hard", "context_cloze_mcq", "Complete: 我喜歡學習。", "學習", ["學習", "吃飯"]),
        ],
    }

    rows = build_question_rows([story], tiers=ALL_TIERS)

    assert len(rows) == 3
    assert {row["tier"] for row in rows} == {"easy", "medium", "hard"}
    assert all(row["source"] == "vocab_assessment" for row in rows)
    assert rows[0]["frame_index"] == ""
    assert rows[0]["correct_answer"] == "to learn"


def test_export_marks_invalid_canonical_items():
    story = {
        "id": "story-2",
        "title": "Invalid story",
        "vocab_assessment": [_question("easy", "basic_meaning_mcq", "", "", ["wrong", "wrong"])],
    }
    validation_rows: list[dict] = []
    rows = build_question_rows([story], validation_rows=validation_rows)
    assert rows[0]["validation_status"] == "error"
    assert "missing_prompt" in rows[0]["validation_errors"]
    assert "duplicate_options" in rows[0]["validation_errors"]
    assert validation_rows[0]["source"] == "vocab_assessment"
