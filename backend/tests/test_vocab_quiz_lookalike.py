"""Confirms /api/vocab-quiz-lookalike generates visually-confusable
Traditional Chinese words (喝/渴-style face-confusion traps for the tier-3
vocab quiz) via Groq (preferred) or Gemini (fallback), converts Simplified
output to Traditional, filters out the word itself and duplicates, caps at
3 per word, falls back between engines on an upstream error, and fails
clearly when neither API key is configured."""
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
    {"word": "喝", "translation": "to drink", "context": "我要喝水。"},
    {"word": "買", "translation": "to buy"},
]

LOOKALIKE_PAYLOAD = [
    # The word itself and the duplicate "渴" are filtered; capped at 3.
    {"word": "喝", "lookalikes": ["渴", "喝", "喂", "渴", "揭", "碣"]},
    # Not one of the requested words — should be dropped.
    {"word": "電腦", "lookalikes": ["雷腦"]},
]


class TestGroqPath:
    def test_generates_and_filters_lookalikes(self, client, with_groq_key, no_gemini_key):
        mock_response = _mock_groq_response(LOOKALIKE_PAYLOAD)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _patched_client(mock_response)
            response = client.post(
                "/api/vocab-quiz-lookalike", json={"words": REQUEST_WORDS}
            )

        assert response.status_code == 200
        results = response.json()["results"]
        assert [r["word"] for r in results] == ["喝"]
        assert results[0]["lookalikes"] == ["渴", "喂", "揭"]

    def test_simplified_output_is_converted_to_traditional(
        self, client, with_groq_key, no_gemini_key
    ):
        payload = [{"word": "買", "lookalikes": ["卖"]}]  # Simplified 賣
        mock_response = _mock_groq_response(payload)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _patched_client(mock_response)
            response = client.post(
                "/api/vocab-quiz-lookalike", json={"words": REQUEST_WORDS}
            )

        assert response.status_code == 200
        assert response.json()["results"][0]["lookalikes"] == ["賣"]

    def test_avoid_list_is_included_in_the_prompt(self, client, with_groq_key, no_gemini_key):
        mock_response = _mock_groq_response(LOOKALIKE_PAYLOAD)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_patched = _patched_client(mock_response)
            mock_client_cls.return_value = mock_patched
            response = client.post(
                "/api/vocab-quiz-lookalike",
                json={
                    "words": [
                        {"word": "喝", "translation": "to drink", "avoid": ["渴", "喂"]},
                    ]
                },
            )

        assert response.status_code == 200
        sent_prompt = mock_patched.post.await_args.kwargs["json"]["messages"][1]["content"]
        assert "already used, do not repeat: 渴, 喂" in sent_prompt


class TestGeminiPath:
    def test_generates_and_filters_lookalikes(self, client, with_gemini_key, no_groq_key):
        mock_response = _mock_gemini_response(LOOKALIKE_PAYLOAD)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _patched_client(mock_response)
            response = client.post(
                "/api/vocab-quiz-lookalike", json={"words": REQUEST_WORDS}
            )

        assert response.status_code == 200
        assert response.json()["results"][0]["lookalikes"] == ["渴", "喂", "揭"]

    def test_upstream_error_returns_502(self, client, with_gemini_key, no_groq_key):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal error"

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _patched_client(mock_response)
            response = client.post(
                "/api/vocab-quiz-lookalike", json={"words": REQUEST_WORDS}
            )

        assert response.status_code == 502


def test_falls_back_to_gemini_when_groq_fails(client, with_groq_key, with_gemini_key):
    groq_error = MagicMock()
    groq_error.status_code = 429
    groq_error.text = "quota exceeded"
    gemini_success = _mock_gemini_response(LOOKALIKE_PAYLOAD)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value = _patched_client(groq_error, gemini_success)
        response = client.post(
            "/api/vocab-quiz-lookalike", json={"words": REQUEST_WORDS}
        )

    assert response.status_code == 200
    assert response.json()["results"][0]["lookalikes"] == ["渴", "喂", "揭"]


def test_missing_both_keys_returns_503(client, no_gemini_key, no_groq_key):
    response = client.post("/api/vocab-quiz-lookalike", json={"words": REQUEST_WORDS})
    assert response.status_code == 503


def test_blank_words_returns_400(client, with_gemini_key):
    response = client.post(
        "/api/vocab-quiz-lookalike",
        json={"words": [{"word": "  ", "translation": ""}]},
    )
    assert response.status_code == 400


class TestPromptSingleAnswerRule:
    def test_prompt_forbids_lookalikes_that_could_also_be_correct(self):
        import main

        prompt = main._vocab_lookalike_prompt(
            [main.VocabLookalikeWord(word="喝", translation="to drink")]
        )
        assert "ONLY correct option" in prompt
