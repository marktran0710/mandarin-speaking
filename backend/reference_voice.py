"""Orchestrates "model voice" reference generation for one story scene:
synthesizes the scene's model sentence via TTS, extracts its pitch contour,
and approximately slices each vocabulary word's own audio clip + reference
pitch-shape curve out of that one recording (see praat_analyzer for why
slicing is approximate rather than exact — edge-tts has no reliable
word-boundary timing for Mandarin).

The result is what gets persisted onto a story frame: a sentence-level
audio URL (reusing the existing listenAudioUrl/listenScript fields) plus a
per-word audio URL + cached scoring curve (vocabularyAudioUrls /
vocabularyReferenceCurves).
"""
import os
import time
from typing import List, Optional, Tuple, TypedDict

import numpy as np

from praat_analyzer import extract_pitch, reference_curve_for_span, slice_reference_word_span
from tts_service import (
    DEFAULT_ZH_VOICE,
    decode_mp3_to_pcm,
    read_wav,
    synthesize_sentence_mp3,
    write_wav,
)


class WordReference(TypedDict):
    word: str
    audio_url: Optional[str]
    curve: List[float]


class SceneReference(TypedDict):
    sentence_audio_url: str
    sentence_script: str
    words: List[WordReference]


def _safe_stem(value: str) -> str:
    return "".join(
        char if char.isalnum() or char in ("-", "_") else "-" for char in value
    ).strip("-") or "story"


async def generate_scene_reference(
    story_id: str,
    frame_index: int,
    sentence_text: str,
    words: List[str],
    audio_dir: str,
    audio_url_prefix: str = "/uploads/story_audio",
    voice: str = DEFAULT_ZH_VOICE,
) -> SceneReference:
    """Generate + save the model-voice audio for one scene.

    ``audio_dir`` is the on-disk directory to save WAV files into (the
    caller's STORY_AUDIO_UPLOAD_DIR); ``audio_url_prefix`` is the matching
    public URL prefix those files are served under.
    """
    text = sentence_text.strip()
    if not text:
        raise ValueError("Scene has no model sentence to synthesize.")

    mp3_bytes = await synthesize_sentence_mp3(text, voice=voice)
    pcm, sample_rate = decode_mp3_to_pcm(mp3_bytes)

    ts = int(time.time() * 1000) % 1_000_000
    stem = f"{_safe_stem(story_id)}-frame-{frame_index}-model-{ts}"
    sentence_filename = f"{stem}.wav"
    sentence_path = os.path.join(audio_dir, sentence_filename)
    write_wav(sentence_path, pcm, sample_rate)

    pitch_contour = extract_pitch(sentence_path)
    word_results = _slice_word_references(
        text, words, pitch_contour, pcm, sample_rate, stem, audio_dir, audio_url_prefix
    )

    return {
        "sentence_audio_url": f"{audio_url_prefix}/{sentence_filename}",
        "sentence_script": text,
        "words": word_results,
    }


def extract_scene_reference_from_audio(
    story_id: str,
    frame_index: int,
    sentence_text: str,
    words: List[str],
    sentence_audio_path: str,
    audio_dir: str,
    audio_url_prefix: str = "/uploads/story_audio",
) -> List[WordReference]:
    """Extracts per-word reference pitch-shape curves + audio clips from a
    scene's real model recording that's already saved on disk — a teacher's
    uploaded file or live mic recording — instead of synthesizing new TTS
    audio. Mirrors the per-word slicing `generate_scene_reference` does for
    TTS output, so a real recording becomes just as valid a scoring target as
    a synthesized one, without re-encoding or duplicating the sentence audio
    itself (the caller already owns that file).
    """
    text = sentence_text.strip()
    if not text:
        raise ValueError("Scene has no model sentence text to align against.")

    pitch_contour = extract_pitch(sentence_audio_path)
    pcm, sample_rate = read_wav(sentence_audio_path)

    ts = int(time.time() * 1000) % 1_000_000
    stem = f"{_safe_stem(story_id)}-frame-{frame_index}-model-{ts}"
    return _slice_word_references(
        text, words, pitch_contour, pcm, sample_rate, stem, audio_dir, audio_url_prefix
    )


def _slice_word_references(
    sentence_text: str,
    words: List[str],
    pitch_contour: List[Tuple[float, float]],
    pcm: np.ndarray,
    sample_rate: int,
    stem: str,
    audio_dir: str,
    audio_url_prefix: str,
) -> List[WordReference]:
    word_results: List[WordReference] = []
    search_from = 0
    for index, word in enumerate(words):
        span = None if not word.strip() else slice_reference_word_span(
            sentence_text, word, pitch_contour, search_from
        )
        if span is None:
            word_results.append({"word": word, "audio_url": None, "curve": []})
            continue

        start, end, search_from = span
        curve = reference_curve_for_span(pitch_contour, start, end)

        start_sample = max(0, int(start * sample_rate))
        end_sample = min(len(pcm), int(end * sample_rate))
        word_pcm = pcm[start_sample:end_sample]

        word_audio_url = None
        if len(word_pcm) > 0:
            word_filename = f"{stem}-word-{index}.wav"
            write_wav(os.path.join(audio_dir, word_filename), word_pcm, sample_rate)
            word_audio_url = f"{audio_url_prefix}/{word_filename}"

        word_results.append({"word": word, "audio_url": word_audio_url, "curve": curve})

    return word_results
