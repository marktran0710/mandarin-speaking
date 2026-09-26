from scripts.manual_bkt_smoke import _response, find_published_triplet


def _item(word, number):
    return {
        "questionId": f"{word}:round{number}:v1",
        "wordId": word,
        "targetWord": word,
        "round": number,
        "correctAnswer": "right",
        "acceptedAnswers": ["right"],
        "pinyin": "rì",
        "options": ["right", "wrong"],
    }


def test_smoke_discovers_real_published_triplet_and_filters_word():
    story = {"id": "published-1", "published": True, "vocabAssessment": [_item("weak", n) for n in (1, 2, 3)]}
    selected, word_id, items = find_published_triplet([story], "weak")
    assert selected["id"] == "published-1"
    assert word_id == "weak"
    assert [items[f"tier{n}"]["questionId"] for n in (1, 2, 3)] == [f"weak:round{n}:v1" for n in (1, 2, 3)]


def test_smoke_payload_uses_published_item_and_does_not_claim_client_grade():
    item = _item("word", 1)
    result = _response(item, "tier1", correct=True)
    assert result["itemId"] == "word:round1:v1"
    assert result["selectedAnswer"] == "right"
    assert result["bktValidationStatus"] == "APPROVED"
    assert result["correct"] is False
