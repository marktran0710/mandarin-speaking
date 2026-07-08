"""Confirms /api/vocab-from-sentence segments a sentence via Groq (preferred)
or Gemini (fallback), filters out hallucinated/duplicate words, falls back
from one engine to the other on an upstream error, and fails clearly when
neither API key is configured."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


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
        "choices": [{"message": {"content": json.dumps({"words": payload})}}]
    }
    return mock_response


def _patched_client(*responses):
    """A mock httpx.AsyncClient whose .post() returns each response in turn
    (one per call) — lets a test drive a Groq-then-Gemini fallback."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=list(responses))
    return mock_client


WORDS_PAYLOAD = [
    {"word": "餐廳", "pinyin": "cāntīng", "pos": "N", "translation": "restaurant"},
    {"word": "吃", "pinyin": "chī", "pos": "V", "translation": "to eat"},
    # Not actually in the sentence — should be dropped.
    {"word": "電腦", "pinyin": "diànnǎo", "pos": "N", "translation": "computer"},
    # Exact duplicate of the first entry — should be deduped.
    {"word": "餐廳", "pinyin": "cāntīng", "pos": "N", "translation": "restaurant"},
]


class TestGroqPath:
    """Groq is tried first when configured."""

    def test_extracts_and_filters_words(self, client, with_groq_key, no_gemini_key):
        mock_response = _mock_groq_response(WORDS_PAYLOAD)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _patched_client(mock_response)
            response = client.post(
                "/api/vocab-from-sentence", json={"sentence": "我在餐廳吃飯。"}
            )

        assert response.status_code == 200
        words = response.json()["words"]
        assert [w["word"] for w in words] == ["餐廳", "吃"]
        assert words[0]["translation"] == "restaurant"

    def test_invalid_pos_is_blanked_out(self, client, with_groq_key, no_gemini_key):
        payload = [{"word": "餐廳", "pinyin": "cāntīng", "pos": "NotARealCode", "translation": "restaurant"}]
        mock_response = _mock_groq_response(payload)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _patched_client(mock_response)
            response = client.post("/api/vocab-from-sentence", json={"sentence": "餐廳"})

        assert response.status_code == 200
        assert response.json()["words"][0]["pos"] == ""


class TestGeminiPath:
    """Gemini is used when Groq isn't configured."""

    def test_extracts_and_filters_words(self, client, with_gemini_key, no_groq_key):
        mock_response = _mock_gemini_response(WORDS_PAYLOAD)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _patched_client(mock_response)
            response = client.post(
                "/api/vocab-from-sentence", json={"sentence": "我在餐廳吃飯。"}
            )

        assert response.status_code == 200
        words = response.json()["words"]
        assert [w["word"] for w in words] == ["餐廳", "吃"]
        assert words[0]["translation"] == "restaurant"

    def test_invalid_pos_is_blanked_out(self, client, with_gemini_key, no_groq_key):
        payload = [{"word": "餐廳", "pinyin": "cāntīng", "pos": "NotARealCode", "translation": "restaurant"}]
        mock_response = _mock_gemini_response(payload)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _patched_client(mock_response)
            response = client.post("/api/vocab-from-sentence", json={"sentence": "餐廳"})

        assert response.status_code == 200
        assert response.json()["words"][0]["pos"] == ""

    def test_upstream_error_returns_502(self, client, with_gemini_key, no_groq_key):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal error"

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _patched_client(mock_response)
            response = client.post(
                "/api/vocab-from-sentence", json={"sentence": "我在餐廳吃飯。"}
            )

        assert response.status_code == 502


def test_falls_back_to_gemini_when_groq_fails(client, with_groq_key, with_gemini_key):
    """Both engines configured, Groq errors (e.g. quota exhausted) — Gemini
    should pick up the request instead of surfacing an error."""
    groq_error = MagicMock()
    groq_error.status_code = 429
    groq_error.text = "quota exceeded"
    gemini_success = _mock_gemini_response(WORDS_PAYLOAD)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value = _patched_client(groq_error, gemini_success)
        response = client.post(
            "/api/vocab-from-sentence", json={"sentence": "我在餐廳吃飯。"}
        )

    assert response.status_code == 200
    assert [w["word"] for w in response.json()["words"]] == ["餐廳", "吃"]


def test_missing_both_keys_returns_503(client, no_gemini_key, no_groq_key):
    response = client.post("/api/vocab-from-sentence", json={"sentence": "我在餐廳吃飯。"})
    assert response.status_code == 503


def test_blank_sentence_returns_400(client, with_gemini_key):
    response = client.post("/api/vocab-from-sentence", json={"sentence": "   "})
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
            "/api/vocab-from-sentence", json={"sentence": "我在餐廳吃飯。"}
        )

    assert response.status_code == 502
