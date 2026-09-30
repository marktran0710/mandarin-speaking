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
    extract_pitch_two_pass,
    reference_curve_for_span,
    slice_reference_word_span,
)
from helpers.pinyin_service import canonical_pinyin
from helpers.audio_io import read_wav, write_wav


class WordReference(TypedDict):
    word: str
    audio_url: Optional[str]
    curve: List[float]


_MODEL_POINTS_PER_TOKEN = 24


class ModelContourToken(TypedDict):
    token: str
    points: List[List[float]]


class SentenceModelContour(TypedDict):
    text: str
    tokens: List[ModelContourToken]


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
    curves, _contour = extract_scene_model_references(sentence_audio_path, sentence_text)
    return curves


def extract_sentence_model_contour(
    sentence_audio_path: str,
    sentence_text: str,
) -> SentenceModelContour:
    """The model recording's whole-sentence pitch shape, for display only.

    See ``extract_scene_model_references``."""
    _curves, contour = extract_scene_model_references(sentence_audio_path, sentence_text)
    return contour


def extract_scene_model_references(
    sentence_audio_path: str,
    sentence_text: str,
) -> Tuple[dict[str, List[float]], SentenceModelContour]:
    """One analysis pass over a teacher recording, returning both the
    per-token scoring curves and the display-only sentence model contour.

    The contour stores, per scored token, points as ``[relative_time,
    semitones]``: time relative to that token's own span (0..1) so the
    student chart can stretch each token onto the student's own timing, and
    pitch in semitones relative to the model speaker's median so only the
    *shape* carries over — a student with a different voice range imitates
    the rises and falls, not the teacher's absolute pitch. It is never read
    by scoring.
    """
    text = sentence_text.strip()
    if not text:
        raise ValueError("Scene has no model sentence text to align against.")

    empty_contour: SentenceModelContour = {"text": text, "tokens": []}
    pitch_contour = extract_pitch(sentence_audio_path)
    if len(pitch_contour) < 2:
        return {}, empty_contour

    analysis = analyze_all(
        sentence_audio_path,
        text,
        pinyin_hint=_tone_hint_for_sentence(text),
    )
    words = analysis[5] or []
    curves: dict[str, List[float]] = {}
    for word in words:
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
    # The model contour drives the on-screen model voice and the similarity
    # score, so it gets the speaker-adaptive tracker; the scoring curves above
    # keep the original tracker and stay exactly as they were.
    model_pitch = extract_pitch_two_pass(sentence_audio_path)
    if len(model_pitch) < 2:
        model_pitch = pitch_contour
    return curves, _sentence_model_contour(text, words, model_pitch)


def _sentence_model_contour(
    text: str,
    words: List[dict],
    pitch_contour: List[Tuple[float, float]],
) -> SentenceModelContour:
    voiced = [float(freq) for _, freq in pitch_contour if float(freq) > 0]
    if not voiced:
        return {"text": text, "tokens": []}
    median_hz = float(np.median(voiced))

    tokens: List[ModelContourToken] = []
    for word in words:
        token = str(word.get("token") or "").strip()
        if not token or not any("\u4e00" <= char <= "\u9fff" for char in token):
            continue
        start = float(word.get("start_time", 0.0))
        end = float(word.get("end_time", 0.0))
        span = end - start
        points = [
            (float(t), float(f))
            for t, f in pitch_contour
            if start <= float(t) <= end and float(f) > 0
        ] if span > 0 else []
        if len(points) > _MODEL_POINTS_PER_TOKEN:
            picks = np.linspace(0, len(points) - 1, _MODEL_POINTS_PER_TOKEN).round().astype(int)
            points = [points[i] for i in picks]
        tokens.append({
            "token": token,
            "points": [
                [round((t - start) / span, 3), round(12.0 * float(np.log2(f / median_hz)), 2)]
                for t, f in points
            ],
        })
    return {"text": text, "tokens": tokens}


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
