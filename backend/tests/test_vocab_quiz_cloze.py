"""Confirms /api/vocab-quiz-cloze generates fill-in-the-blank sentences plus
wrong-word options via Groq (preferred) or Gemini (fallback), filters out
candidates whose sentence doesn't actually contain the target word, falls
back from one engine to the other on an upstream error, and fails clearly
when neither API key is configured."""
import json
from unittest.mock import AsyncMock, MagicMock, patch


def _mock_gemini_response(payload):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]
    }
    return mock_response


def _mock_groq_response(payload):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": json.dumps({"results": payload})}}]
    }
    return mock_response


def _patched_client(*responses):
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=list(responses))
    return mock_client


REQUEST_WORDS = [
    {"word": "餐廳", "translation": "restaurant", "context": "我在餐廳吃飯。"},
    {"word": "吃", "translation": "to eat"},
]

CLOZE_PAYLOAD = [
    {
        "word": "餐廳",
        "sentence": "我們今天要去餐廳吃飯。",
        "distractors": ["教室", "公園", "餐廳", "醫院"],
    },
    # Sentence doesn't actually contain the word — should be dropped.
    {"word": "吃", "sentence": "他喜歡運動。", "distractors": ["喝", "看"]},
    # Not one of the requested words — should be dropped.
    {"word": "電腦", "sentence": "我有一台電腦。", "distractors": ["手機"]},
]


class TestGroqPath:
    def test_generates_and_filters_cloze_results(self, client, with_groq_key, no_gemini_key):
        mock_response = _mock_groq_response(CLOZE_PAYLOAD)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _patched_client(mock_response)
            response = client.post("/api/vocab-quiz-cloze", json={"words": REQUEST_WORDS})

        assert response.status_code == 200
        results = response.json()["results"]
        assert [r["word"] for r in results] == ["餐廳"]
        assert results[0]["sentence"] == "我們今天要去餐廳吃飯。"
        # The word itself ("餐廳") is filtered out of its own distractor list,
        # capped at 3.
        assert results[0]["distractors"] == ["教室", "公園", "醫院"]

    def test_avoid_list_is_included_in_the_prompt(self, client, with_groq_key, no_gemini_key):
        mock_response = _mock_groq_response(CLOZE_PAYLOAD)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_patched = _patched_client(mock_response)
            mock_client_cls.return_value = mock_patched
            response = client.post(
                "/api/vocab-quiz-cloze",
                json={
                    "words": [
                        {
                            "word": "餐廳",
                            "translation": "restaurant",
                            "avoid": ["我在餐廳吃飯。"],
                        },
                    ]
                },
            )

        assert response.status_code == 200
        sent_prompt = mock_patched.post.await_args.kwargs["json"]["messages"][1]["content"]
        assert "already used, write a different sentence: 我在餐廳吃飯。" in sent_prompt


class TestGeminiPath:
    def test_generates_and_filters_cloze_results(self, client, with_gemini_key, no_groq_key):
        mock_response = _mock_gemini_response(CLOZE_PAYLOAD)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _patched_client(mock_response)
            response = client.post("/api/vocab-quiz-cloze", json={"words": REQUEST_WORDS})

        assert response.status_code == 200
        results = response.json()["results"]
        assert results[0]["distractors"] == ["教室", "公園", "醫院"]

    def test_upstream_error_returns_502(self, client, with_gemini_key, no_groq_key):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal error"

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _patched_client(mock_response)
            response = client.post("/api/vocab-quiz-cloze", json={"words": REQUEST_WORDS})

        assert response.status_code == 502


def test_falls_back_to_gemini_when_groq_fails(client, with_groq_key, with_gemini_key):
    groq_error = MagicMock()
    groq_error.status_code = 429
    groq_error.text = "quota exceeded"
    gemini_success = _mock_gemini_response(CLOZE_PAYLOAD)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value = _patched_client(groq_error, gemini_success)
        response = client.post("/api/vocab-quiz-cloze", json={"words": REQUEST_WORDS})

    assert response.status_code == 200
    assert response.json()["results"][0]["distractors"] == ["教室", "公園", "醫院"]


def test_missing_both_keys_returns_503(client, no_gemini_key, no_groq_key):
    response = client.post("/api/vocab-quiz-cloze", json={"words": REQUEST_WORDS})
    assert response.status_code == 503


def test_blank_words_returns_400(client, with_gemini_key):
    response = client.post(
        "/api/vocab-quiz-cloze",
        json={"words": [{"word": "  ", "translation": ""}]},
    )
    assert response.status_code == 400


def test_converts_simplified_chinese_output_to_traditional(client, with_groq_key, no_gemini_key):
    # The model sometimes ignores the Traditional-Chinese instruction. A
    # Simplified sentence containing 餐厅 (not 餐廳) would otherwise fail the
    # "sentence must contain word" check and get silently dropped, in
    # addition to just being the wrong script for this Traditional-Chinese app.
    simplified_payload = [
        {
            "word": "餐廳",
            "sentence": "我们今天要去餐厅吃饭。",
            "distractors": ["教室", "公园", "医院"],
        },
    ]
    mock_response = _mock_groq_response(simplified_payload)
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value = _patched_client(mock_response)
        response = client.post(
            "/api/vocab-quiz-cloze",
            json={"words": [{"word": "餐廳", "translation": "restaurant"}]},
        )

    assert response.status_code == 200
    results = response.json()["results"]
    assert results[0]["sentence"] == "我們今天要去餐廳吃飯。"
    assert results[0]["distractors"] == ["教室", "公園", "醫院"]


def test_both_engines_failing_returns_502(client, with_groq_key, with_gemini_key):
    groq_error = MagicMock()
    groq_error.status_code = 500
    groq_error.text = "groq internal error"
    gemini_error = MagicMock()
    gemini_error.status_code = 500
    gemini_error.text = "gemini internal error"

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value = _patched_client(groq_error, gemini_error)
        response = client.post("/api/vocab-quiz-cloze", json={"words": REQUEST_WORDS})

    assert response.status_code == 502


class TestPromptSingleAnswerRule:
    def test_prompt_forbids_distractors_that_also_fit_the_blank(self):
        import main

        prompt = main._vocab_cloze_prompt(
            [main.VocabClozeWord(word="高興", translation="happy")]
        )
        assert "may correctly fill the blank" in prompt
