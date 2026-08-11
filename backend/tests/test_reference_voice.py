"""Integration test for reference_voice.generate_scene_reference: only the
network TTS call + MP3 decode are mocked (no network access, no MP3 codec
dependency in CI); the rest — writing a real WAV, running real Praat pitch
extraction, slicing, and normalizing — runs for real so a break anywhere in
that chain shows up here.
"""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from reference_voice import (
    extract_scene_reference_from_audio,
    generate_scene_reference,
    synthesize_best_reference_audio,
)
from tts_service import write_wav


def _synthetic_rising_tone_pcm(duration=1.6, sample_rate=24000):
    """A synthetic voiced sine tone rising from 150 Hz to 220 Hz — enough
    for Praat's pitch tracker to lock onto without needing a real TTS voice."""
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    freq = 150 + 70 * (t / duration)
    phase = 2 * np.pi * np.cumsum(freq) / sample_rate
    pcm = 0.3 * np.sin(phase).astype(np.float32)
    return pcm, sample_rate


@pytest.fixture
def mocked_tts(tmp_path):
    pcm, sample_rate = _synthetic_rising_tone_pcm()
    with patch("reference_voice.synthesize_sentence_mp3", new_callable=AsyncMock) as synth, \
         patch("reference_voice.decode_mp3_to_pcm") as decode:
        synth.return_value = b"fake-mp3-bytes"
        decode.return_value = (pcm, sample_rate)
        yield tmp_path


def test_generates_sentence_and_word_audio(mocked_tts):
    result = asyncio.run(
        generate_scene_reference(
            story_id="story-1",
            frame_index=2,
            sentence_text="我想喝水",
            words=["我", "喝水", "不在"],
            audio_dir=str(mocked_tts),
        )
    )

    assert result["sentence_script"] == "我想喝水"
    assert result["sentence_audio_url"].startswith("/uploads/story_audio/")
    sentence_filename = result["sentence_audio_url"].rsplit("/", 1)[-1]
    assert (mocked_tts / sentence_filename).exists()

    words = result["words"]
    assert [w["word"] for w in words] == ["我", "喝水", "不在"]

    # "我" and "喝水" appear in the sentence text -> should get real clips.
    for w in words[:2]:
        assert w["audio_url"] is not None
        assert len(w["curve"]) == 100
        filename = w["audio_url"].rsplit("/", 1)[-1]
        path = mocked_tts / filename
        assert path.exists()
        data, sr = sf.read(str(path))
        assert len(data) > 0
        assert sr > 0

    # "不在" never appears in "我想喝水" -> no clip, no curve, no crash.
    assert words[2]["audio_url"] is None
    assert words[2]["curve"] == []


def test_word_positions_are_in_reading_order(mocked_tts):
    result = asyncio.run(
        generate_scene_reference(
            story_id="story-2",
            frame_index=0,
            sentence_text="我喜歡咖啡，你也喜歡咖啡",
            words=["咖啡", "咖啡"],
            audio_dir=str(mocked_tts),
        )
    )
    words = result["words"]
    assert words[0]["audio_url"] is not None
    assert words[1]["audio_url"] is not None
    # Two occurrences of the same word should resolve to two distinct clips,
    # not the same one twice (search_from must advance between matches).
    assert words[0]["audio_url"] != words[1]["audio_url"]


def test_extract_from_existing_audio(tmp_path):
    """A teacher's uploaded/recorded WAV (no TTS involved at all) should
    yield the same kind of per-word curves as the TTS path — this is what
    lets a real recording become the scoring target, not just a synthesized
    one."""
    pcm, sample_rate = _synthetic_rising_tone_pcm()
    sentence_path = tmp_path / "teacher-recording.wav"
    write_wav(str(sentence_path), pcm, sample_rate)

    words = extract_scene_reference_from_audio(
        story_id="story-4",
        frame_index=1,
        sentence_text="我想喝水",
        words=["我", "喝水", "不在"],
        sentence_audio_path=str(sentence_path),
        audio_dir=str(tmp_path),
    )

    assert [w["word"] for w in words] == ["我", "喝水", "不在"]
    for w in words[:2]:
        assert w["audio_url"] is not None
        assert len(w["curve"]) == 100
        filename = w["audio_url"].rsplit("/", 1)[-1]
        assert (tmp_path / filename).exists()
    assert words[2]["audio_url"] is None
    assert words[2]["curve"] == []


def test_extract_from_existing_audio_blank_sentence_raises(tmp_path):
    pcm, sample_rate = _synthetic_rising_tone_pcm()
    sentence_path = tmp_path / "teacher-recording.wav"
    write_wav(str(sentence_path), pcm, sample_rate)

    with pytest.raises(ValueError):
        extract_scene_reference_from_audio(
            story_id="story-5",
            frame_index=0,
            sentence_text="   ",
            words=[],
            sentence_audio_path=str(sentence_path),
            audio_dir=str(tmp_path),
        )


def test_blank_sentence_raises(mocked_tts):
    with pytest.raises(ValueError):
        asyncio.run(
            generate_scene_reference(
                story_id="story-3",
                frame_index=0,
                sentence_text="   ",
                words=[],
                audio_dir=str(mocked_tts),
            )
        )


def test_best_reference_skips_a_failed_voice(tmp_path):
    pcm, sample_rate = _synthetic_rising_tone_pcm()
    analysis = [None] * 8
    analysis[3] = 91.0
    analysis[5] = [{"syllables": [{"passed": True}]}]
    analysis[7] = 82.0

    with patch(
        "reference_voice.synthesize_sentence_mp3",
        new_callable=AsyncMock,
        side_effect=[RuntimeError("temporary voice failure"), b"working-mp3"],
    ), patch("reference_voice.decode_mp3_to_pcm", return_value=(pcm, sample_rate)), patch(
        "reference_voice.analyze_all", return_value=analysis
    ):
        result = asyncio.run(
            synthesize_best_reference_audio(
                "妳這個週末要做什麼？",
                voices=("voice-that-fails", "voice-that-works"),
            )
        )

    assert result["voice"] == "voice-that-works"
    assert result["syllable_pass_ratio"] == 1.0
