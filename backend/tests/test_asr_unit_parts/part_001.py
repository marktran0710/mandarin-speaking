"""
Unit tests for the ASR (Automatic Speech Recognition) pipeline.

Coverage:
  - clean_api_key()
  - transcribe_audio_content() routing
  - transcribe_with_auto_fallback() fallback chain
  - transcribe_with_openai() / transcribe_with_gemini() (mocked HTTP)
  - transcribe_with_ct_whisper() (mocked model)
  - /api/transcribe endpoint (integration via TestClient)
  - fallback_language_feedback() from ai_feedback
"""

import os
import sys
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
from fastapi import HTTPException

# Make backend/ importable when running from backend/tests/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from fixtures import SILENT_WAV, SHORT_WAV, LONG_WAV, SPEECH_WAV


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

class TestCleanApiKey:
    def test_none_returns_none(self):
        from main import clean_api_key
        assert clean_api_key(None) is None

    def test_empty_string_returns_none(self):
        from main import clean_api_key
        assert clean_api_key("") is None

    def test_whitespace_returns_none(self):
        from main import clean_api_key
        assert clean_api_key("   ") is None

    def test_placeholder_your_key_returns_none(self):
        from main import clean_api_key
        assert clean_api_key("your_api_key_here") is None
        assert clean_api_key("YOUR_GEMINI_KEY") is None

    def test_placeholder_suffix_returns_none(self):
        from main import clean_api_key
        assert clean_api_key("put_your_key_here") is None

    def test_valid_key_returned_stripped(self):
        from main import clean_api_key
        assert clean_api_key("  sk-abc123  ") == "sk-abc123"

    def test_real_looking_openai_key(self):
        from main import clean_api_key
        key = "sk-proj-abcdefghij1234567890"
        assert clean_api_key(key) == key


# ──────────────────────────────────────────────────────────────────────────────
# transcribe_audio_content routing
# ──────────────────────────────────────────────────────────────────────────────

class TestTranscribeAudioContentRouting:

    @pytest.mark.asyncio
    async def test_auto_routes_to_fallback(self):
        from main import transcribe_audio_content
        with patch("main.transcribe_with_auto_fallback", new_callable=AsyncMock) as mock:
            mock.return_value = MagicMock(text="你好", model="auto:ctwhisper")
            result = await transcribe_audio_content(SPEECH_WAV, "auto")
            mock.assert_awaited_once_with(SPEECH_WAV, vocab_hint="")
            assert result.text == "你好"

    @pytest.mark.asyncio
    async def test_openai_routes_to_openai(self, with_openai_key):
        from main import transcribe_audio_content
        with patch("main.transcribe_with_openai", new_callable=AsyncMock) as mock:
            mock.return_value = MagicMock(text="你好", model="openai")
            result = await transcribe_audio_content(SPEECH_WAV, "openai")
            mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_openai_without_key_raises_500(self, no_openai_key):
        from main import transcribe_audio_content
        with pytest.raises(HTTPException) as exc_info:
            await transcribe_audio_content(SPEECH_WAV, "openai")
        assert exc_info.value.status_code == 500
        assert "OpenAI" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_gemini_routes_to_gemini(self, with_gemini_key):
        from main import transcribe_audio_content
        with patch("main.transcribe_with_gemini", new_callable=AsyncMock) as mock:
            mock.return_value = MagicMock(text="你好", model="gemini")
            result = await transcribe_audio_content(SPEECH_WAV, "gemini")
            mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_gemini_without_key_raises_500(self, no_gemini_key):
        from main import transcribe_audio_content
        with pytest.raises(HTTPException) as exc_info:
            await transcribe_audio_content(SPEECH_WAV, "gemini")
        assert exc_info.value.status_code == 500
        assert "Gemini" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_ctwhisper_alias(self):
        from main import transcribe_audio_content
        with patch("main.transcribe_with_ct_whisper", new_callable=AsyncMock) as mock:
            mock.return_value = MagicMock(text="謝謝", model="ctwhisper")
            await transcribe_audio_content(SPEECH_WAV, "ctwhisper")
            mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_chinese_taiwanese_whisper_alias(self):
        from main import transcribe_audio_content
        with patch("main.transcribe_with_ct_whisper", new_callable=AsyncMock) as mock:
            mock.return_value = MagicMock(text="謝謝", model="ctwhisper")
            await transcribe_audio_content(SPEECH_WAV, "chinese_taiwanese_whisper")
            mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_vibevoice_routes_correctly(self):
        from main import transcribe_audio_content
        with patch("main.transcribe_with_vibevoice", new_callable=AsyncMock) as mock:
            mock.return_value = MagicMock(text="再見", model="vibevoice")
            await transcribe_audio_content(SPEECH_WAV, "vibevoice")
            mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unknown_model_raises_400(self):
        from main import transcribe_audio_content
        with pytest.raises(HTTPException) as exc_info:
            await transcribe_audio_content(SPEECH_WAV, "nonexistent_model")
        assert exc_info.value.status_code == 400


# ──────────────────────────────────────────────────────────────────────────────
# Auto-fallback chain
# ──────────────────────────────────────────────────────────────────────────────

class TestTranscribeWithAutoFallback:

    @pytest.mark.asyncio
    async def test_returns_first_successful_provider(self, monkeypatch):
        import main
        monkeypatch.setattr(main, "ASR_FALLBACK_ORDER", ["ctwhisper", "vibevoice"])
        with patch("main.transcribe_with_ct_whisper", new_callable=AsyncMock) as mock_ctw:
            mock_ctw.return_value = MagicMock(text="你好", model="ctwhisper")
            result = await main.transcribe_with_auto_fallback(SPEECH_WAV)
        assert result.text == "你好"
        assert "auto:ctwhisper" in result.model

    @pytest.mark.asyncio
    async def test_skips_to_next_on_failure(self, monkeypatch):
        import main
        monkeypatch.setattr(main, "ASR_FALLBACK_ORDER", ["ctwhisper", "vibevoice"])
        with patch("main.transcribe_with_ct_whisper", new_callable=AsyncMock) as ctw, \
             patch("main.transcribe_with_vibevoice", new_callable=AsyncMock) as vibevoicem:
            ctw.side_effect = RuntimeError("model not loaded")
            vibevoicem.return_value = MagicMock(text="早上好", model="vibevoice")
            result = await main.transcribe_with_auto_fallback(SPEECH_WAV)
        assert result.text == "早上好"
        assert "vibevoice" in result.model

    @pytest.mark.asyncio
    async def test_skips_empty_transcription(self, monkeypatch):
        import main
        monkeypatch.setattr(main, "ASR_FALLBACK_ORDER", ["ctwhisper", "vibevoice"])
        with patch("main.transcribe_with_ct_whisper", new_callable=AsyncMock) as ctw, \
             patch("main.transcribe_with_vibevoice", new_callable=AsyncMock) as vibevoicem:
            ctw.return_value = MagicMock(text="   ", model="ctwhisper")  # empty
            vibevoicem.return_value = MagicMock(text="謝謝", model="vibevoice")
            result = await main.transcribe_with_auto_fallback(SPEECH_WAV)
        assert result.text == "謝謝"

    @pytest.mark.asyncio
    async def test_raises_503_when_all_fail(self, monkeypatch):
        import main
        monkeypatch.setattr(main, "ASR_FALLBACK_ORDER", ["ctwhisper"])
        with patch("main.transcribe_with_ct_whisper", new_callable=AsyncMock) as ctw:
            ctw.side_effect = RuntimeError("model missing")
            with pytest.raises(HTTPException) as exc_info:
                await main.transcribe_with_auto_fallback(SPEECH_WAV)
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_skips_gemini_without_key(self, monkeypatch, no_gemini_key):
        import main
        monkeypatch.setattr(main, "ASR_FALLBACK_ORDER", ["gemini", "ctwhisper"])
        with patch("main.transcribe_with_ct_whisper", new_callable=AsyncMock) as ctw:
            ctw.return_value = MagicMock(text="你好", model="ctwhisper")
            result = await main.transcribe_with_auto_fallback(SPEECH_WAV)
        assert result.text == "你好"

    @pytest.mark.asyncio
    async def test_skips_openai_without_key(self, monkeypatch, no_openai_key):
        import main
        monkeypatch.setattr(main, "ASR_FALLBACK_ORDER", ["openai", "ctwhisper"])
        with patch("main.transcribe_with_ct_whisper", new_callable=AsyncMock) as ctw:
            ctw.return_value = MagicMock(text="早上好", model="ctwhisper")
            result = await main.transcribe_with_auto_fallback(SPEECH_WAV)
        assert result.text == "早上好"


# ──────────────────────────────────────────────────────────────────────────────
# OpenAI provider (mocked HTTP)
# ──────────────────────────────────────────────────────────────────────────────

class TestTranscribeWithOpenAI:

    @pytest.mark.asyncio
    async def test_successful_transcription(self, with_openai_key):
        from main import transcribe_with_openai
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "你好世界"}

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await transcribe_with_openai(SILENT_WAV)

        assert result.text == "你好世界"
        assert result.model == "openai"

    @pytest.mark.asyncio
    async def test_api_error_raises_exception(self, with_openai_key):
        from main import transcribe_with_openai
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            with pytest.raises(Exception, match="OpenAI API error"):
                await transcribe_with_openai(SILENT_WAV)

    @pytest.mark.asyncio
    async def test_sends_correct_model_and_language(self, with_openai_key):
        from main import transcribe_with_openai
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "再見"}

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            await transcribe_with_openai(SILENT_WAV)

            _, kwargs = mock_client.post.call_args
            assert kwargs["data"]["model"] == "whisper-1"
            assert kwargs["data"]["language"] == "zh"


# ──────────────────────────────────────────────────────────────────────────────
# Gemini provider (mocked HTTP)
# ──────────────────────────────────────────────────────────────────────────────

class TestTranscribeWithGemini:

    @pytest.mark.asyncio
    async def test_successful_transcription(self, with_gemini_key):
        from main import transcribe_with_gemini
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [
                {"content": {"parts": [{"text": "早上好"}]}}
            ]
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await transcribe_with_gemini(SILENT_WAV)

        assert result.text == "早上好"
        assert result.model == "gemini"

    @pytest.mark.asyncio
    async def test_api_error_raises_exception(self, with_gemini_key):
        from main import transcribe_with_gemini
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            with pytest.raises(Exception, match="Gemini API error"):
                await transcribe_with_gemini(SILENT_WAV)

    @pytest.mark.asyncio
    async def test_base64_encodes_audio(self, with_gemini_key):
        import base64
        from main import transcribe_with_gemini
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "謝謝"}]}}]
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            await transcribe_with_gemini(SHORT_WAV)

            _, kwargs = mock_client.post.call_args
            payload = kwargs["json"]
            inline_data = payload["contents"][0]["parts"][0]["inline_data"]
            decoded = base64.b64decode(inline_data["data"])
            assert decoded == SHORT_WAV
