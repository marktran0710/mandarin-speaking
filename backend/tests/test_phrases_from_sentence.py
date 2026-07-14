"""Confirms /api/phrases-from-sentence extracts phrase-level chunks via Groq
(preferred) or Gemini (fallback), filters out hallucinated/duplicate
phrases, falls back from one engine to the other on an upstream error, and
fails clearly when neither API key is configured."""
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
        "choices": [{"message": {"content": json.dumps({"phrases": payload})}}]
    }
    return mock_response


def _patched_client(*responses):
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=list(responses))
    return mock_client


PHRASES_PAYLOAD = [
    {"phrase": "想要", "translation": "want to"},
    {"phrase": "在餐廳", "translation": "at the restaurant"},
    # Not actually in the sentence — should be dropped.
    {"phrase": "去電腦", "translation": "go to the computer"},
    # Exact duplicate of the first entry — should be deduped.
    {"phrase": "想要", "translation": "want to"},
]


class TestGroqPath:
    def test_extracts_and_filters_phrases(self, client, with_groq_key, no_gemini_key):
        mock_response = _mock_groq_response(PHRASES_PAYLOAD)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _patched_client(mock_response)
            response = client.post(
                "/api/phrases-from-sentence",
                json={"sentence": "我想要在餐廳吃飯。", "count": 2},
            )

        assert response.status_code == 200
        phrases = response.json()["phrases"]
        assert [p["phrase"] for p in phrases] == ["想要", "在餐廳"]
        assert phrases[0]["translation"] == "want to"

    def test_count_is_forwarded_to_the_prompt(self, client, with_groq_key, no_gemini_key):
        mock_response = _mock_groq_response(PHRASES_PAYLOAD)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_patched = _patched_client(mock_response)
            mock_client_cls.return_value = mock_patched
            client.post(
                "/api/phrases-from-sentence",
                json={"sentence": "我想要在餐廳吃飯。", "count": 3},
            )

        sent_prompt = mock_patched.post.await_args.kwargs["json"]["messages"][1]["content"]
        assert "up to 3" in sent_prompt


class TestGeminiPath:
    def test_extracts_and_filters_phrases(self, client, with_gemini_key, no_groq_key):
        mock_response = _mock_gemini_response(PHRASES_PAYLOAD)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _patched_client(mock_response)
            response = client.post(
                "/api/phrases-from-sentence",
                json={"sentence": "我想要在餐廳吃飯。", "count": 2},
            )

        assert response.status_code == 200
        phrases = response.json()["phrases"]
        assert [p["phrase"] for p in phrases] == ["想要", "在餐廳"]

    def test_upstream_error_returns_502(self, client, with_gemini_key, no_groq_key):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal error"

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _patched_client(mock_response)
            response = client.post(
                "/api/phrases-from-sentence", json={"sentence": "我想要在餐廳吃飯。"}
            )

        assert response.status_code == 502


def test_falls_back_to_gemini_when_groq_fails(client, with_groq_key, with_gemini_key):
    groq_error = MagicMock()
    groq_error.status_code = 429
    groq_error.text = "quota exceeded"
    gemini_success = _mock_gemini_response(PHRASES_PAYLOAD)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value = _patched_client(groq_error, gemini_success)
        response = client.post(
            "/api/phrases-from-sentence", json={"sentence": "我想要在餐廳吃飯。"}
        )

    assert response.status_code == 200
    assert [p["phrase"] for p in response.json()["phrases"]] == ["想要", "在餐廳"]


def test_missing_both_keys_returns_503(client, no_gemini_key, no_groq_key):
    response = client.post(
        "/api/phrases-from-sentence", json={"sentence": "我想要在餐廳吃飯。"}
    )
    assert response.status_code == 503


def test_blank_sentence_returns_400(client, with_gemini_key):
    response = client.post("/api/phrases-from-sentence", json={"sentence": "   "})
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
            "/api/phrases-from-sentence", json={"sentence": "我想要在餐廳吃飯。"}
        )

    assert response.status_code == 502
