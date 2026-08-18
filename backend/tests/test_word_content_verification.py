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
    async def test_extra_text_does_not_match_a_word_target(self):
        from main import _verify_word_transcription
        with patch("main.transcribe_audio_content", new_callable=AsyncMock) as mock:
            mock.return_value = MagicMock(text="你好嗎", model="auto:ctwhisper")
            recognized, match = await _verify_word_transcription(SILENT_WAV, "你好")
        assert recognized == "你好嗎"
        assert match is False

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_exact_word_alignment_matches(self):
        from main import _verify_word_transcription
        with patch("main.transcribe_audio_content", new_callable=AsyncMock) as mock:
            mock.return_value = MagicMock(text="abc", model="auto:ctwhisper")
            recognized, match = await _verify_word_transcription(SILENT_WAV, "abc")
        assert recognized == "abc"
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
    async def test_unverifiable_when_recognized_text_empty(self):
        """Empty ASR output means "couldn't hear", not "wrong word".

        Whisper routinely returns nothing for 1-2s single-syllable clips
        (e.g. a student drilling 在) — treating that as a mismatch blocked
        passing drills from ever firing onPass. Empty is unverifiable
        (None), the same fail-open contract as an ASR error.
        """
        from main import _verify_word_transcription
        with patch("main.transcribe_audio_content", new_callable=AsyncMock) as mock:
            mock.return_value = MagicMock(text="   ", model="auto:ctwhisper")
            recognized, match = await _verify_word_transcription(SILENT_WAV, "你好")
        assert recognized == ""
        assert match is None

    @pytest.mark.asyncio
    async def test_fails_open_on_asr_error(self):
        from main import _verify_word_transcription
        with patch("main.transcribe_audio_content", new_callable=AsyncMock) as mock:
            mock.side_effect = RuntimeError("all ASR providers failed")
            recognized, match = await _verify_word_transcription(SILENT_WAV, "你好")
        assert recognized is None
        assert match is None

    @pytest.mark.asyncio
    async def test_rejects_one_wrong_syllable_in_a_longer_phrase(self):
        """PhrasePracticeDrill sends a whole multi-character phrase as the
        verify target. A single homophone/ASR slip on one syllable used to
        fail the entire phrase's content check (exact substring), which then
        forced can_score_pronunciation=False and showed students a "not
        enough clear pitch evidence" retry message for what was actually a
        content-verification ASR slip, not a recording-quality problem."""
        from main import _verify_word_transcription
        target = "妳這個週末要做什麼"
        heard = "妳這個週未要做什麼"  # 末 -> 未, one-character ASR slip
        with patch("main.transcribe_audio_content", new_callable=AsyncMock) as mock:
            mock.return_value = MagicMock(text=heard, model="auto:ctwhisper")
            recognized, match = await _verify_word_transcription(SILENT_WAV, target)
        assert recognized == heard
        assert match is False

    @pytest.mark.asyncio
    async def test_still_rejects_a_mostly_wrong_longer_phrase(self):
        from main import _verify_word_transcription
        target = "妳這個週末要做什麼"
        heard = "完全不一樣的句子內容"
        with patch("main.transcribe_audio_content", new_callable=AsyncMock) as mock:
            mock.return_value = MagicMock(text=heard, model="auto:ctwhisper")
            recognized, match = await _verify_word_transcription(SILENT_WAV, target)
        assert recognized == heard
        assert match is False

    @pytest.mark.asyncio
    async def test_still_requires_an_exact_match_for_short_targets(self):
        """Below MIN_CONTENT_MATCH_CHARS a character-overlap ratio can't
        distinguish "said it out of order" from "said the right word" (same
        reasoning the frontend's scriptMatchRatio gate already applies), so
        short single-word/character targets keep the strict, order-sensitive
        exact-substring behavior instead of the longer-phrase ratio match.
        Both characters of "你好" appear in "好你在家" (reordered), which a
        bag-of-characters ratio would accept — the exact-substring check
        correctly still rejects it."""
        from main import _verify_word_transcription
        with patch("main.transcribe_audio_content", new_callable=AsyncMock) as mock:
            mock.return_value = MagicMock(text="好你在家", model="auto:ctwhisper")
            recognized, match = await _verify_word_transcription(SILENT_WAV, "你好")
        assert recognized == "好你在家"
        assert match is False

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
