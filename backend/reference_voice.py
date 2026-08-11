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
import tempfile
import time
from typing import List, Optional, Tuple, TypedDict

import numpy as np

from praat_analyzer import (
    analyze_all,
    extract_pitch,
    reference_curve_for_span,
    slice_reference_word_span,
)
from pinyin_service import canonical_pinyin
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
    sentence_reference_curves: dict[str, List[float]]


REFERENCE_VOICES = (
    "zh-TW-HsiaoChenNeural",
    "zh-TW-HsiaoYuNeural",
    "zh-TW-YunJheNeural",
)


class BestTtsAudio(TypedDict):
    mp3_bytes: bytes
    pcm: np.ndarray
    sample_rate: int
    voice: str
    tone_accuracy: float
    fluency_score: float
    syllable_pass_ratio: float


def _tone_hint_for_sentence(sentence_text: str) -> str:
    hanzi = "".join(
        char for char in sentence_text if "\u4e00" <= char <= "\u9fff"
    )
    return canonical_pinyin(hanzi)


async def synthesize_best_reference_audio(
    sentence_text: str,
    voices: Tuple[str, ...] = REFERENCE_VOICES,
) -> BestTtsAudio:
    """Generate several Taiwan-Mandarin candidates and keep the best one.

    The scorer deliberately ranks syllable pass coverage before fluency so a
    learner receives the clearest tonal model available from the configured
    TTS voices. This is a selection step, not a promise that TTS is human-
    perfect; the returned metrics are exposed to reference-QC callers.
    """
    text = sentence_text.strip()
    if not text:
        raise ValueError("Scene has no model sentence to synthesize.")

    best: BestTtsAudio | None = None
    best_rank = -1.0
    candidate_errors: List[str] = []
    pinyin_hint = _tone_hint_for_sentence(text)
    for voice in voices:
        temporary_path = ""
        try:
            mp3_bytes = await synthesize_sentence_mp3(text, voice=voice)
            pcm, sample_rate = decode_mp3_to_pcm(mp3_bytes)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as handle:
                temporary_path = handle.name
            write_wav(temporary_path, pcm, sample_rate)
            analysis = analyze_all(
                temporary_path,
                text,
                pinyin_hint=pinyin_hint,
            )
            word_prosody = analysis[5] or []
            syllables = [
                syllable
                for word in word_prosody
                for syllable in word.get("syllables") or []
                if syllable.get("passed") is not None
            ]
            pass_ratio = (
                sum(syllable.get("passed") is True for syllable in syllables)
                / len(syllables)
                if syllables
                else 0.0
            )
            tone_accuracy = float(analysis[7] or 0.0)
            fluency_score = float(analysis[3] or 0.0)
            # A clear pass across every target syllable is more useful to a
            # learner than a slightly smoother voice with one failed tone.
            rank = pass_ratio * 65.0 + tone_accuracy * 0.25 + fluency_score * 0.10
            current = {
                "mp3_bytes": mp3_bytes,
                "pcm": pcm,
                "sample_rate": sample_rate,
                "voice": voice,
                "tone_accuracy": round(tone_accuracy, 1),
                "fluency_score": round(fluency_score, 1),
                "syllable_pass_ratio": round(pass_ratio, 3),
            }
            if best is None or rank > best_rank:
                best = current
                best_rank = rank
        except Exception as exc:
            # A transient edge-tts/network failure for one voice should not
            # discard the other Taiwan voices that may still be available.
            candidate_errors.append(f"{voice}: {exc}")
            continue
        finally:
            if temporary_path and os.path.exists(temporary_path):
                os.unlink(temporary_path)

    if best is None:
        detail = "; ".join(candidate_errors[-3:])
        suffix = f" ({detail})" if detail else ""
        raise RuntimeError(
            "No usable Taiwan-Mandarin TTS candidate was produced." + suffix
        )
    return best


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

    if voice == DEFAULT_ZH_VOICE:
        best = await synthesize_best_reference_audio(text)
        mp3_bytes = best["mp3_bytes"]
        pcm = best["pcm"]
        sample_rate = best["sample_rate"]
    else:
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
    sentence_reference_curves = extract_scene_reference_curves(sentence_path, text)

    return {
        "sentence_audio_url": f"{audio_url_prefix}/{sentence_filename}",
        "sentence_script": text,
        "words": word_results,
        "sentence_reference_curves": sentence_reference_curves,
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


def extract_scene_reference_curves(
    sentence_audio_path: str,
    sentence_text: str,
) -> dict[str, List[float]]:
    """Extract real pitch-shape curves for every scored scene token.

    Vocabulary clips are useful for vocabulary cards, but pronunciation
    scoring also evaluates function words and the full target sentence. Use
    the same token alignment as student analysis so those tokens do not fall
    back to a synthetic tone template when a teacher/TTS recording exists.
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
