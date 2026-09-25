"""Derive pronunciation references from a real uploaded model recording.

The teacher's audio is kept as the sentence-level model clip and is also
approximately sliced into per-word clips plus cached pitch-shape curves.
There is deliberately no synthesis fallback here: missing model audio stays
missing until a teacher uploads a recording.
"""
import os
import time
from typing import List, Optional, Tuple, TypedDict

import numpy as np

from domain.speech.acoustics import (
    analyze_all,
    extract_pitch,
    reference_curve_for_span,
    slice_reference_word_span,
)
from helpers.pinyin_service import canonical_pinyin
from helpers.audio_io import read_wav, write_wav


class WordReference(TypedDict):
    word: str
    audio_url: Optional[str]
    curve: List[float]


def _tone_hint_for_sentence(sentence_text: str) -> str:
    hanzi = "".join(
        char for char in sentence_text if "\u4e00" <= char <= "\u9fff"
    )
    return canonical_pinyin(hanzi)


def _safe_stem(value: str) -> str:
    return "".join(
        char if char.isalnum() or char in ("-", "_") else "-" for char in value
    ).strip("-") or "story"


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
    uploaded file or live mic recording; no synthesis is performed.
    audio. The same slicing logic is used for every uploaded model recording,
    without re-encoding or duplicating the sentence audio
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


def extract_scene_reference_curves(
    sentence_audio_path: str,
    sentence_text: str,
) -> dict[str, List[float]]:
    """Extract real pitch-shape curves for every scored scene token.

    Vocabulary clips are useful for vocabulary cards, but pronunciation
    scoring also evaluates function words and the full target sentence. Use
    the same token alignment as student analysis so those tokens do not fall
    back to a synthetic tone template when a teacher recording exists.
    """
    text = sentence_text.strip()
    if not text:
        raise ValueError("Scene has no model sentence text to align against.")

    pitch_contour = extract_pitch(sentence_audio_path)
    if len(pitch_contour) < 2:
        return {}

    analysis = analyze_all(
        sentence_audio_path,
        text,
        pinyin_hint=_tone_hint_for_sentence(text),
    )
    curves: dict[str, List[float]] = {}
    for word in analysis[5] or []:
        token = str(word.get("token") or "").strip()
        if not token or not word.get("expected_tones"):
            continue
        curve = reference_curve_for_span(
            pitch_contour,
            float(word.get("start_time", 0.0)),
            float(word.get("end_time", 0.0)),
        )
        if curve:
            curves.setdefault(token, curve)
    return curves


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
