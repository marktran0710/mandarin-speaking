"""Unit tests for _verify_word_transcription (per-word ASR content check).

Word-practice callers pass the target word as the `transcription` so Praat
scores tone against a known reference. That path never actually confirms the
student said the right word. _verify_word_transcription runs an independent
ASR pass to catch that mismatch without touching the tone-scoring path.
"""
import os
import sys

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from fixtures import SILENT_WAV


class TestVerifyWordTranscription:

    @pytest.mark.asyncio
    async def test_match_when_word_present_in_recognized_text(self):
        from main import _verify_word_transcription
        with patch("main.transcribe_audio_content", new_callable=AsyncMock) as mock:
            mock.return_value = MagicMock(text="你好嗎", model="auto:ctwhisper")
            recognized, match = await _verify_word_transcription(SILENT_WAV, "你好")
        assert recognized == "你好嗎"
        assert match is True

    @pytest.mark.asyncio
    async def test_no_match_when_word_absent(self):
        from main import _verify_word_transcription
        with patch("main.transcribe_audio_content", new_callable=AsyncMock) as mock:
            mock.return_value = MagicMock(text="再見", model="auto:ctwhisper")
            recognized, match = await _verify_word_transcription(SILENT_WAV, "你好")
        assert recognized == "再見"
        assert match is False

    @pytest.mark.asyncio
    async def test_no_match_when_recognized_text_empty(self):
        from main import _verify_word_transcription
        with patch("main.transcribe_audio_content", new_callable=AsyncMock) as mock:
            mock.return_value = MagicMock(text="   ", model="auto:ctwhisper")
            recognized, match = await _verify_word_transcription(SILENT_WAV, "你好")
        assert recognized == ""
        assert match is False

    @pytest.mark.asyncio
    async def test_fails_open_on_asr_error(self):
        from main import _verify_word_transcription
        with patch("main.transcribe_audio_content", new_callable=AsyncMock) as mock:
            mock.side_effect = RuntimeError("all ASR providers failed")
            recognized, match = await _verify_word_transcription(SILENT_WAV, "你好")
        assert recognized is None
        assert match is None

    @pytest.mark.asyncio
    async def test_prefers_groq_when_key_configured(self, with_groq_key):
        from main import _verify_word_transcription
        with patch("main.transcribe_audio_content", new_callable=AsyncMock) as mock:
            mock.return_value = MagicMock(text="你好", model="groq")
            await _verify_word_transcription(SILENT_WAV, "你好")
        mock.assert_awaited_once_with(SILENT_WAV, "groq", vocab_hint="你好")

    @pytest.mark.asyncio
    async def test_falls_back_to_auto_chain_without_groq_key(self, no_groq_key):
        from main import _verify_word_transcription
        with patch("main.transcribe_audio_content", new_callable=AsyncMock) as mock:
            mock.return_value = MagicMock(text="你好", model="auto:ctwhisper")
            await _verify_word_transcription(SILENT_WAV, "你好")
        mock.assert_awaited_once_with(SILENT_WAV, "auto", vocab_hint="你好")

    @pytest.mark.asyncio
    async def test_uses_explicit_vocab_hint_when_provided(self, with_groq_key):
        from main import _verify_word_transcription
        with patch("main.transcribe_audio_content", new_callable=AsyncMock) as mock:
            mock.return_value = MagicMock(text="你好", model="groq")
            await _verify_word_transcription(SILENT_WAV, "你好", vocab_hint="你好, 再見, 謝謝")
        mock.assert_awaited_once_with(SILENT_WAV, "groq", vocab_hint="你好, 再見, 謝謝")
