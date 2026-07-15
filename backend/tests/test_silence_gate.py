"""The silence gate in front of every ASR provider: silent/noise-only audio
must never reach a Whisper model (they hallucinate on silence — worst case
echoing the vocab-hint prompt back as the 'transcript'), stock phantom
phrases must be filtered, and an all-empty auto chain is a silent recording,
not a 503 server error."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from fixtures import SILENT_WAV, SPEECH_WAV, make_tone_wav_bytes

import main
from main import (
    _filter_asr_phantoms,
    _has_speech,
    transcribe_audio_content,
)


class TestHasSpeech:
    def test_silence_is_not_speech(self):
        assert _has_speech(SILENT_WAV) is False

    def test_loud_sustained_tone_is_speech(self):
        assert _has_speech(SPEECH_WAV) is True

    def test_quiet_hum_below_rms_threshold_is_not_speech(self):
        quiet = make_tone_wav_bytes(1.0, amplitude=0.005)
        assert _has_speech(quiet) is False

    def test_brief_pop_is_not_speech(self):
        # Loud but far shorter than the 0.4s voiced-duration floor.
        pop = make_tone_wav_bytes(0.05, amplitude=0.5)
        assert _has_speech(pop) is False

    def test_undecodable_audio_fails_open(self):
        # A non-WAV blob must assume speech — the gate may only ever
        # prevent hallucinations, never block a real recording.
        assert _has_speech(b"\x1aE\xdf\xa3 not a wav file") is True


class TestPhantomFilter:
    @pytest.mark.parametrize("phantom", [
        "謝謝",
        "謝謝觀看",
        "謝謝觀看。",
        "Thank you.",
        "thank you for watching",
        "字幕由 Amara.org 社群提供",
    ])
    def test_known_phantoms_become_empty(self, phantom):
        assert _filter_asr_phantoms(phantom) == ""

    @pytest.mark.parametrize("real", [
        "我想要去餐廳吃飯",
        "謝謝你的幫忙",  # longer than the stock outro phrase — a real sentence
        "老師好",
    ])
    def test_real_speech_passes_through(self, real):
        assert _filter_asr_phantoms(real) == real


class TestSilenceGateShortCircuit:
    @pytest.mark.asyncio
    async def test_silent_audio_never_reaches_a_provider(self):
        with patch("main.transcribe_with_ct_whisper", new_callable=AsyncMock) as mock:
            result = await transcribe_audio_content(SILENT_WAV, "ctwhisper")
        mock.assert_not_awaited()
        assert result.text == ""
        assert result.model == "silence-gate"

    @pytest.mark.asyncio
    async def test_silent_audio_skips_the_whole_auto_chain(self):
        with patch("main.transcribe_with_auto_fallback", new_callable=AsyncMock) as mock:
            result = await transcribe_audio_content(SILENT_WAV, "auto")
        mock.assert_not_awaited()
        assert result.model == "silence-gate"


class TestAutoAllEmptyIsSilentNotError:
    @pytest.mark.asyncio
    async def test_all_empty_providers_return_empty_response(self, monkeypatch):
        monkeypatch.setattr(main, "ASR_FALLBACK_ORDER", ["ctwhisper", "funasr"])
        with patch("main.transcribe_with_ct_whisper", new_callable=AsyncMock) as ctw, \
             patch("main.transcribe_with_funasr", new_callable=AsyncMock) as funasr:
            ctw.return_value = MagicMock(text="", model="ctwhisper")
            funasr.return_value = MagicMock(text="  ", model="funasr")
            result = await main.transcribe_with_auto_fallback(SPEECH_WAV)
        assert result.text == ""
        assert result.model == "auto:silent"


def test_default_fallback_order_prefers_groq():
    assert main.ASR_FALLBACK_ORDER[0] == "groq"
    assert "ctwhisper" in main.ASR_FALLBACK_ORDER
