"""Tests for extracting references from a real teacher model recording."""

import os
import sys

import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from helpers.audio_io import write_wav
from services.speech.reference_voice import extract_scene_reference_from_audio


def _synthetic_rising_tone_pcm(duration=1.6, sample_rate=24000):
    """Create a voiced rising tone for the pitch tracker."""
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    freq = 150 + 70 * (t / duration)
    phase = 2 * np.pi * np.cumsum(freq) / sample_rate
    pcm = 0.3 * np.sin(phase).astype(np.float32)
    return pcm, sample_rate


def test_extract_from_existing_audio(tmp_path):
    """Teacher audio produces per-word clips and reference curves."""
    pcm, sample_rate = _synthetic_rising_tone_pcm()
    sentence_path = tmp_path / "teacher-recording.wav"
    write_wav(str(sentence_path), pcm, sample_rate)

    words = extract_scene_reference_from_audio(
        story_id="story-4",
        frame_index=1,
        sentence_text="\u6211\u60f3\u559d\u6c34",
        words=["\u6211", "\u559d\u6c34", "\u4e0d\u5728"],
        sentence_audio_path=str(sentence_path),
        audio_dir=str(tmp_path),
    )

    assert [word["word"] for word in words] == ["\u6211", "\u559d\u6c34", "\u4e0d\u5728"]
    for word in words[:2]:
        assert word["audio_url"] is not None
        assert len(word["curve"]) == 100
        filename = word["audio_url"].rsplit("/", 1)[-1]
        path = tmp_path / filename
        assert path.exists()
        data, sample_rate = sf.read(str(path))
        assert len(data) > 0
        assert sample_rate > 0
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
