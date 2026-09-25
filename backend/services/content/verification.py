"""Recording-quality preflight, the feedback quality gate, and independent
ASR-based content verification: whether a recording has enough acoustic
evidence to score at all, and whether what the student said actually
matches the target word/sentence.

This does NOT compute tone/pronunciation scores itself (that's
chinese_tones.py/praat_analyzer.py/tone_decision.py, plus
services/pronunciation_scoring.py) — it decides whether the evidence
those scorers produced can be trusted and shown to the student, and
independently checks the *content* (right word/sentence) against the ASR
transcript.
"""

from __future__ import annotations

import io
import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

import services.asr as asr_service
from config import settings
from helpers.pinyin_service import canonical_pinyin_tone3
from services.asr import transcribe_audio_content
from services.text_normalization import convert_to_traditional_chinese

logger = logging.getLogger("speaking_app")

_MAX_AUDIO_BYTES = settings.max_audio_bytes

# Silence gate: audio with less energy/voiced speech than this never reaches
# an ASR model at all. Whisper-family models hallucinate on silence — worst
# of all by echoing the vocab-hint prompt back as the "transcript", which
# scores a student who said nothing as if they'd said the target words.
# Thresholds match the earlier prod-hardening tuning: 0.005 RMS let fan/room
# hum through, 0.02 doesn't; 0.4s of voiced audio rejects pops and hum that
# still pass RMS.
ASR_SILENCE_RMS = settings.asr_silence_rms
ASR_MIN_SPEECH_SECONDS = settings.asr_min_speech_seconds
FEEDBACK_MIN_DURATION_SECONDS = settings.feedback_min_duration_seconds
FEEDBACK_MAX_CLIPPING_RATIO = settings.feedback_max_clipping_ratio
FEEDBACK_MIN_PITCH_POINTS = settings.feedback_min_pitch_points


def _decode_wav_mono(audio_content: bytes) -> Tuple[np.ndarray, int]:
    """Decode PCM WAV bytes to mono float32 in [-1, 1] using only the stdlib
    — librosa/soundfile are optional deps that may not exist on the deployed
    backend, and every in-app recording path already produces WAV."""
    import wave

    with wave.open(io.BytesIO(audio_content)) as wav_file:
        sample_rate = wav_file.getframerate()
        sample_width = wav_file.getsampwidth()
        channels = wav_file.getnchannels()
        raw = wav_file.readframes(wav_file.getnframes())

    dtype = {1: np.int8, 2: np.int16, 4: np.int32}.get(sample_width)
    if dtype is None:
        raise ValueError(f"Unsupported WAV sample width: {sample_width}")
    data = np.frombuffer(raw, dtype=dtype).astype(np.float32)
    data /= float(2 ** (8 * sample_width - 1))
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return data, sample_rate


def _target_syllable_count(text: str) -> Optional[int]:
    """Return a conservative target-unit count for recording preflight."""
    normalized = (text or "").strip()
    if not normalized:
        return None
    han_count = sum(1 for char in normalized if "㐀" <= char <= "鿿")
    if han_count:
        return han_count
    units = [unit for unit in normalized.split() if unit]
    return len(units) or None


def assess_recording_quality(
    audio_content: bytes,
    *,
    expected_syllable_count: Optional[int] = None,
) -> Dict[str, Any]:
    """Measure whether a recording contains enough evidence for feedback.

    This is deliberately deterministic and provider-independent.  It runs
    before cloud AI so silence/noise cannot be turned into a confident
    transcript by a generative model.  Decode failures require ``review`` rather
    than rejected because non-WAV uploads may still be valid audio that the
    provider can decode.
    """
    try:
        data, sample_rate = _decode_wav_mono(audio_content)
    except Exception as exc:
        logger.info("Recording-quality preflight could not decode WAV: %s", exc)
        return {
            "status": "review",
            "confidence": 0.25,
            "can_score_pronunciation": False,
            "can_score_content": False,
            "reason_codes": ["audio_format_unverified"],
            "student_message": (
                "We could not verify this recording's sound quality. Please record again "
                "as WAV before using the result for practice decisions."
            ),
            "metrics": {},
        }

    duration = len(data) / sample_rate if sample_rate > 0 else 0.0
    rms = float(np.sqrt(np.mean(data**2))) if len(data) else 0.0
    peak = float(np.max(np.abs(data))) if len(data) else 0.0
    clipping_ratio = float(np.mean(np.abs(data) >= 0.99)) if len(data) else 0.0

    frame = max(1, int(sample_rate * 0.025))
    hop = max(1, int(sample_rate * 0.010))
    voiced_seconds = 0.0
    voiced_ratio = 0.0
    energy_variation = 0.0
    if len(data) >= frame and peak > 0:
        windows = np.lib.stride_tricks.sliding_window_view(data, frame)[::hop]
        frame_rms = np.sqrt(np.mean(windows**2, axis=1))
        frame_peak = float(frame_rms.max()) if len(frame_rms) else 0.0
        if frame_peak > 0:
            mean_frame_rms = float(np.mean(frame_rms))
            if mean_frame_rms > 0:
                energy_variation = float(np.std(frame_rms) / mean_frame_rms)
            # Require both an absolute speech floor and proximity to the
            # recording's loudest frame.  The absolute floor stops steady
            # room hum from declaring its entire duration "voiced".
            voiced = (
                (frame_rms >= ASR_SILENCE_RMS * 0.5)
                & (frame_rms > frame_peak * 10 ** (-30 / 20))
            )
            voiced_seconds = float(np.sum(voiced)) * hop / sample_rate
            voiced_ratio = min(1.0, voiced_seconds / max(duration, 0.001))

    metrics = {
        "duration_seconds": round(duration, 3),
        "rms": round(rms, 5),
        "peak": round(peak, 5),
        "clipping_ratio": round(clipping_ratio, 5),
        "voiced_seconds": round(voiced_seconds, 3),
        "voiced_ratio": round(voiced_ratio, 3),
        "energy_variation": round(energy_variation, 3),
        "pitch_points": 0,
    }
    # A one-syllable target can be a perfectly valid short utterance. The
    # generic 0.4s floor rejected the supplied 好 recording even though it
    # contained 0.329s of voiced audio inside a 0.656s clip. Keep the stricter
    # floor for phrases, but allow a single target syllable down to 0.25s.
    minimum_voiced_seconds = (
        min(ASR_MIN_SPEECH_SECONDS, 0.25)
        if expected_syllable_count == 1
        else ASR_MIN_SPEECH_SECONDS
    )
    reasons: List[str] = []
    if duration < FEEDBACK_MIN_DURATION_SECONDS:
        reasons.append("recording_too_short")
    if rms < ASR_SILENCE_RMS:
        reasons.append("signal_too_quiet")
    if voiced_seconds < minimum_voiced_seconds:
        reasons.append("insufficient_speech")
    if clipping_ratio > FEEDBACK_MAX_CLIPPING_RATIO:
        reasons.append("audio_clipping")

    if reasons:
        return {
            "status": "retry",
            "confidence": 0.0,
            "can_score_pronunciation": False,
            "can_score_content": False,
            "reason_codes": reasons,
            "student_message": "Move closer and say the full phrase again.",
            "metrics": metrics,
        }

    # Preflight proves that audible signal exists, not yet that Praat found
    # enough voiced pitch or that ASR recognized the intended content.
    signal_confidence = min(
        0.8,
        0.35
        + min(0.25, voiced_seconds / max(minimum_voiced_seconds, 0.01) * 0.1)
        + min(0.2, voiced_ratio * 0.25),
    )
    review_reasons = ["awaiting_acoustic_analysis"]
    # A nearly constant, fully voiced signal is often a calibration tone,
    # electrical hum, or held vowel rather than a complete practice attempt.
    # Do not reject it as silence, but never let it become mastery evidence.
    if voiced_ratio >= 0.85 and energy_variation < 0.03:
        review_reasons.append("low_signal_variation")

    return {
        "status": "review",
        "confidence": round(signal_confidence, 2),
        "can_score_pronunciation": False,
        "can_score_content": False,
        "reason_codes": review_reasons,
        "student_message": "The recording passed the sound check; analyzing speech evidence now.",
        "metrics": metrics,
    }


def finalize_feedback_quality(
    preflight: Dict[str, Any],
    pitch_contour: List[Tuple[float, float]],
    transcription: str,
    *,
    content_match: Optional[bool] = None,
    content_was_verified: bool = False,
) -> Dict[str, Any]:
    """Combine signal, pitch and transcript evidence into the API quality gate."""
    quality = {
        **preflight,
        "metrics": dict(preflight.get("metrics") or {}),
        "reason_codes": list(preflight.get("reason_codes") or []),
    }
    quality["metrics"]["pitch_points"] = len(pitch_contour)

    if quality.get("status") == "retry":
        return quality

    reasons = [r for r in quality["reason_codes"] if r != "awaiting_acoustic_analysis"]
    pitch_ok = len(pitch_contour) >= FEEDBACK_MIN_PITCH_POINTS
    transcript_ok = bool(transcription.strip())
    if not pitch_ok:
        reasons.append("insufficient_voiced_pitch")
    if not transcript_ok:
        reasons.append("transcription_unavailable")
    if content_match is False:
        reasons.append("target_content_mismatch")

    # A content mismatch must block the content pass, but it should not erase
    # useful acoustic feedback for the words that were actually spoken. An
    # unknown verification result still blocks pronunciation scoring because
    # there is no safe target-to-audio mapping yet.
    target_available_for_pronunciation = (
        not content_was_verified or content_match is not None
    )
    if content_was_verified and content_match is None:
        reasons.append("target_content_unverified")
    can_score_pronunciation = (
        pitch_ok and transcript_ok and target_available_for_pronunciation
    )
    can_score_content = (
        transcript_ok
        and content_was_verified
        and content_match is True
    )
    if transcript_ok and not content_was_verified:
        reasons.append("content_not_independently_verified")
    signal_review_required = any(
        reason in {"audio_format_unverified", "low_signal_variation"}
        for reason in reasons
    )
    if signal_review_required:
        can_score_content = False

    if not can_score_pronunciation:
        status = "retry" if not pitch_ok or not transcript_ok else "review"
        confidence = 0.0 if status == "retry" else 0.4
        message = (
            "We could not collect enough clear speech and pitch evidence to score this "
            "attempt safely. Please record it once more."
        )
    else:
        status = (
            "reliable"
            if can_score_content and not signal_review_required
            else "review"
        )
        pitch_confidence = min(1.0, len(pitch_contour) / max(FEEDBACK_MIN_PITCH_POINTS * 4, 1))
        confidence = round(min(0.95, 0.55 + pitch_confidence * 0.4), 2)
        message = (
            "This recording has enough evidence for pronunciation feedback."
            if status == "reliable"
            else "Pronunciation can be scored, but the spoken content could not be confirmed."
        )

    return {
        **quality,
        "status": status,
        "confidence": confidence,
        "can_score_pronunciation": can_score_pronunciation,
        "can_score_content": can_score_content,
        "reason_codes": reasons,
        "student_message": message,
    }


def _normalized_scene_content_units(value: str) -> list[str]:
    """Return comparable sentence units while ignoring script/punctuation noise."""
    normalized = convert_to_traditional_chinese(value or "")
    return [char for char in normalized if char.isalnum()]


def _content_unit_key(unit: str) -> str:
    """Return a tone-insensitive key for one ASR-comparable character."""
    if not unit:
        return ""
    if unit.isascii():
        return unit.casefold()
    try:
        reading = canonical_pinyin_tone3(unit).strip().split()
        if reading:
            syllable = reading[0]
            return syllable[:-1] if syllable[-1:] in "12345" else syllable
    except Exception:
        pass
    return unit


def _content_units_equivalent(target: str, recognized: str) -> bool:
    return bool(target) and _content_unit_key(target) == _content_unit_key(recognized)


def _missing_scene_content_units(target: str, recognized: str) -> list[str]:
    """List target units in missing/replaced alignment spans, in target order."""
    return [
        segment["target"]
        for segment in _align_scene_content(target, recognized)
        if segment["type"] in {"missing", "replace"} and segment["target"]
    ]


def _align_scene_content(target: str, recognized: str) -> list[dict[str, str]]:
    """Align target and ASR units while treating pinyin homophones as matches."""
    target_units = _normalized_scene_content_units(target)
    recognized_units = _normalized_scene_content_units(recognized)
    rows = len(target_units)
    cols = len(recognized_units)
    if not target_units or not recognized_units:
        return []

    costs = [[0] * (cols + 1) for _ in range(rows + 1)]
    for row in range(1, rows + 1):
        costs[row][0] = row
    for col in range(1, cols + 1):
        costs[0][col] = col
    for row in range(1, rows + 1):
        for col in range(1, cols + 1):
            diagonal = costs[row - 1][col - 1] + (
                0 if _content_units_equivalent(target_units[row - 1], recognized_units[col - 1]) else 1
            )
            costs[row][col] = min(diagonal, costs[row - 1][col] + 1, costs[row][col - 1] + 1)

    operations: list[dict[str, str]] = []
    row, col = rows, cols
    while row or col:
        if row and col:
            equivalent = _content_units_equivalent(target_units[row - 1], recognized_units[col - 1])
            diagonal = costs[row - 1][col - 1] + (0 if equivalent else 1)
            if costs[row][col] == diagonal:
                operations.append({
                    "type": "match" if equivalent else "replace",
                    "target": target_units[row - 1],
                    "heard": recognized_units[col - 1],
                })
                row -= 1
                col -= 1
                continue
        if row and costs[row][col] == costs[row - 1][col] + 1:
            operations.append({"type": "missing", "target": target_units[row - 1], "heard": ""})
            row -= 1
            continue
        operations.append({"type": "extra", "target": "", "heard": recognized_units[col - 1]})
        col -= 1

    operations.reverse()
    grouped: list[dict[str, str]] = []
    for operation in operations:
        if grouped and grouped[-1]["type"] == operation["type"]:
            grouped[-1]["target"] += operation["target"]
            grouped[-1]["heard"] += operation["heard"]
        else:
            grouped.append(dict(operation))
    return grouped


def _scene_content_diff(target: str, recognized: str) -> list[dict[str, str]]:
    """Return display-ready contiguous spans, or no fake diff for empty ASR."""
    if not _normalized_scene_content_units(target) or not _normalized_scene_content_units(recognized):
        return []
    return _align_scene_content(target, recognized)


def _scene_content_match(target: str, recognized: str) -> Optional[bool]:
    """Verify a sentence while tolerating homophone ASR substitutions.

    Matching is positional and length-preserving. This prevents an omitted
    name or phrase from passing merely because most of the remaining sentence
    overlaps, while still allowing substitutions such as 友/遊 and 妳/你.
    """
    target_units = _normalized_scene_content_units(target)
    recognized_units = _normalized_scene_content_units(recognized)
    if not target_units or not recognized_units:
        return None

    return all(segment["type"] == "match" for segment in _align_scene_content(target, recognized))


def _acoustic_scoring_source(
    sentence_target: str, scene_content_match: Optional[bool]
) -> str:
    """Which transcript to run pitch/tone scoring against for this sentence.

    ``scene_content_match is False`` is real negative evidence (the ASR
    content check actually disagreed with the target) — scoring against the
    known-correct sentence in that case would fabricate a score for words the
    learner may not have said, so the raw ASR transcript is used instead.
    ``None`` is not that: it means the check never ran or couldn't confirm
    anything (verify_word drill in progress, empty transcript, ASR/model
    hiccup) — an unrelated verification gap, not evidence the learner got it
    wrong. Falling back to the ASR transcript in that case silently truncates
    scoring to whatever (possibly partial or mis-heard) text the ASR
    produced, which can measure far fewer syllables than the sentence
    actually has. Only a confirmed mismatch should give up the known-correct
    target; an unverified result fails open, same as the content_match gates
    in storyRecorderFeedback.ts and build_pronunciation_mastery.
    """
    if sentence_target and scene_content_match is not False:
        return "scene_target"
    return "asr_transcript"


async def _verify_word_transcription(
    audio_content: bytes, word: str, vocab_hint: str = ""
) -> Tuple[Optional[str], Optional[bool]]:
    """Runs an independent ASR pass to check whether `word` was actually spoken.

    Word-practice callers pass the target word as the `transcription` so Praat
    scores tone against a known reference instead of a possibly-wrong ASR guess.
    That means tone scoring never actually confirms the student said the right
    word. This runs ASR for real, on the side, purely to catch that mismatch.
    Fails open (None, None) on ASR error so a transcription hiccup never blocks
    the pitch/tone feedback the student came for.

    `word` may be a single vocabulary word/character or, for phrase-practice
    callers, an entire multi-character phrase — requiring the whole string to
    appear verbatim was fine for short targets but made phrase verification
    fail outright whenever the independent ASR pass misheard a single
    syllable anywhere in a longer phrase (common, not rare). Longer targets
    use the same tolerant character-overlap ratio the frontend already
    applies for its own pass/fail verdict, so the two no longer disagree.

    Prefers Groq (fast, cloud) over the "auto" chain's default of the local
    ctwhisper model, which is CPU-heavy and — running alongside the Praat
    analysis on every single word attempt — made word practice noticeably
    slower once this check was added.
    """
    model = "groq" if asr_service.GROQ_API_KEY else "auto"
    try:
        result = await transcribe_audio_content(audio_content, model, vocab_hint=vocab_hint or word)
        recognized = convert_to_traditional_chinese(result.text).strip()
        if not recognized:
            # ASR heard nothing — on a 1-2s single-syllable drill clip
            # that's an ASR limitation, not evidence the wrong word was
            # spoken. Unverifiable (None), the same fail-open contract as
            # an ASR error; a hard False here silently blocked passing
            # drills from ever clearing their mastery chip.
            return recognized, None
        return recognized, _scene_content_match(word, recognized)
    except Exception as exc:
        logger.warning("Word content verification failed: %s", exc)
        return None, None


def build_analysis_description(
    transcription: str,
    transcription_model: str,
    word_prosody: list[dict],
) -> str:
    text = transcription.strip()
    word_count = len(word_prosody)

    if not text:
        return (
            "The audio was analyzed for pitch and fluency, but no transcript was "
            "returned. Try a clearer recording with one short sentence."
        )

    model_note = (
        f" using {transcription_model}"
        if transcription_model
        else ""
    )
    return (
        f"The system transcribed your recording{model_note} and found "
        f"{word_count} word-level prosody item{'s' if word_count != 1 else ''} "
        "for review."
    )
