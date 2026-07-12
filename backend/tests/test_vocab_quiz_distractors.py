"""Confirms /api/vocab-quiz-distractors generates plausible wrong-answer
translations via Groq (preferred) or Gemini (fallback), filters out
distractors that match the correct translation or duplicate each other,
caps at 3 per word, falls back from one engine to the other on an upstream
error, and fails clearly when neither API key is configured."""
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

DISTRACTORS_PAYLOAD = [
    {"word": "餐廳", "distractors": ["kitchen", "hotel", "restaurant", "kitchen", "cafeteria"]},
    # Not one of the requested words — should be dropped.
    {"word": "電腦", "distractors": ["phone", "tablet"]},
]


class TestGroqPath:
    def test_generates_and_filters_distractors(self, client, with_groq_key, no_gemini_key):
        mock_response = _mock_groq_response(DISTRACTORS_PAYLOAD)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _patched_client(mock_response)
            response = client.post(
                "/api/vocab-quiz-distractors", json={"words": REQUEST_WORDS}
            )

        assert response.status_code == 200
        results = response.json()["results"]
        assert [r["word"] for r in results] == ["餐廳"]
        # The correct translation ("restaurant") and the duplicate "kitchen"
        # are filtered; capped at 3 distractors.
        assert results[0]["distractors"] == ["kitchen", "hotel", "cafeteria"]

    def test_avoid_list_is_included_in_the_prompt(self, client, with_groq_key, no_gemini_key):
        mock_response = _mock_groq_response(DISTRACTORS_PAYLOAD)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_patched = _patched_client(mock_response)
            mock_client_cls.return_value = mock_patched
            response = client.post(
                "/api/vocab-quiz-distractors",
                json={
                    "words": [
                        {"word": "餐廳", "translation": "restaurant", "avoid": ["kitchen", "hotel"]},
                    ]
                },
            )

        assert response.status_code == 200
        sent_prompt = mock_patched.post.await_args.kwargs["json"]["messages"][1]["content"]
        assert "already used, do not repeat: kitchen, hotel" in sent_prompt


class TestGeminiPath:
    def test_generates_and_filters_distractors(self, client, with_gemini_key, no_groq_key):
        mock_response = _mock_gemini_response(DISTRACTORS_PAYLOAD)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _patched_client(mock_response)
            response = client.post(
                "/api/vocab-quiz-distractors", json={"words": REQUEST_WORDS}
            )

        assert response.status_code == 200
        results = response.json()["results"]
        assert results[0]["distractors"] == ["kitchen", "hotel", "cafeteria"]

    def test_upstream_error_returns_502(self, client, with_gemini_key, no_groq_key):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal error"

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _patched_client(mock_response)
            response = client.post(
                "/api/vocab-quiz-distractors", json={"words": REQUEST_WORDS}
            )

        assert response.status_code == 502


def test_falls_back_to_gemini_when_groq_fails(client, with_groq_key, with_gemini_key):
    groq_error = MagicMock()
    groq_error.status_code = 429
    groq_error.text = "quota exceeded"
    gemini_success = _mock_gemini_response(DISTRACTORS_PAYLOAD)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value = _patched_client(groq_error, gemini_success)
        response = client.post(
            "/api/vocab-quiz-distractors", json={"words": REQUEST_WORDS}
        )

    assert response.status_code == 200
    assert response.json()["results"][0]["distractors"] == ["kitchen", "hotel", "cafeteria"]


def test_missing_both_keys_returns_503(client, no_gemini_key, no_groq_key):
    response = client.post("/api/vocab-quiz-distractors", json={"words": REQUEST_WORDS})
    assert response.status_code == 503


def test_blank_words_returns_400(client, with_gemini_key):
    response = client.post(
        "/api/vocab-quiz-distractors",
        json={"words": [{"word": "  ", "translation": ""}]},
    )
    assert response.status_code == 400


def test_both_engines_failing_returns_502(client, with_groq_key, with_gemini_key):
    groq_error = MagicMock()
    groq_error.status_code = 500
    groq_error.text = "groq internal error"
    gemini_error = MagicMock()
    gemini_error.status_code = 500
    gemini_error.text = "gemini internal error"

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value = _patched_client(groq_error, gemini_error)
        response = client.post(
            "/api/vocab-quiz-distractors", json={"words": REQUEST_WORDS}
        )

    assert response.status_code == 502
