"""
Praat acoustic analysis helpers powered by Parselmouth.

Parselmouth embeds Praat's analysis routines in Python, so the API can extract
pitch and formant features without shelling out to the Praat desktop app.
"""
import re
import wave
from typing import Dict, List, Tuple

import numpy as np

try:
    import parselmouth
except ImportError as exc:
    parselmouth = None
    PARSELMOUTH_IMPORT_ERROR = exc
else:
    PARSELMOUTH_IMPORT_ERROR = None


def _load_sound(audio_path: str):
    if parselmouth is None:
        raise RuntimeError(
            "Praat analysis requires the praat-parselmouth package. "
            "Install backend requirements with: pip install -r backend/requirements.txt"
        ) from PARSELMOUTH_IMPORT_ERROR

    try:
        return parselmouth.Sound(audio_path)
    except Exception as exc:
        raise RuntimeError(
            "Praat could not read this audio file. Send WAV audio for analysis."
        ) from exc


def _pitch_contour_from_sound(
    sound,
    time_step: float = 0.025,
    pitch_floor: float = 75,
    pitch_ceiling: float = 500,
) -> List[Tuple[float, float]]:
    pitch = sound.to_pitch(
        time_step=time_step,
        pitch_floor=pitch_floor,
        pitch_ceiling=pitch_ceiling,
    )
    freqs = pitch.selected_array["frequency"]
    times = pitch.xs()
    contour = [
        (float(times[i]), float(f))
        for i, f in enumerate(freqs)
        if f > 0
    ]
    return _correct_octave_jumps(contour)


def _correct_octave_jumps(
    contour: List[Tuple[float, float]],
    jump_ratio: float = 1.7,
) -> List[Tuple[float, float]]:
    """Fix half/double-frequency errors that pitch trackers occasionally make.

    Praat's autocorrelation pitch tracker sometimes locks onto an octave of the
    true F0 for a frame or two (common on creaky or breathy voices). A lone
    point that jumps by roughly 2x relative to both neighbors is corrected by
    halving/doubling it back toward the local pitch level rather than left to
    distort tone-shape and statistics downstream.
    """
    if len(contour) < 3:
        return contour

    freqs = [f for _, f in contour]
    corrected = list(freqs)
    for i in range(1, len(freqs) - 1):
        prev_f, cur_f, next_f = corrected[i - 1], freqs[i], corrected[i + 1]
        neighbor_avg = (prev_f + next_f) / 2.0
        if neighbor_avg <= 0:
            continue

        ratio = cur_f / neighbor_avg
        if ratio > jump_ratio:
            candidate = cur_f / 2.0
        elif ratio < 1.0 / jump_ratio:
            candidate = cur_f * 2.0
        else:
            continue

        # Only accept the halved/doubled value if it actually lands closer to
        # the local pitch level than the raw reading did.
        if abs(candidate - neighbor_avg) < abs(cur_f - neighbor_avg):
            corrected[i] = candidate

    return [(t, corrected[i]) for i, (t, _) in enumerate(contour)]


def _formants_from_sound(
    sound,
    max_formant: float = 5500,
    num_formants: int = 5,
) -> Dict[str, float]:
    """Return median F1-F3 using Parselmouth's native time grid (avoids 360 Python calls)."""
    formant = sound.to_formant_burg(
        time_step=0.025,
        max_number_of_formants=num_formants,
        maximum_formant=max_formant,
    )
    times = formant.xs()
    values: Dict[str, List[float]] = {"F1": [], "F2": [], "F3": []}
    for t in times:
        for fn, key in ((1, "F1"), (2, "F2"), (3, "F3")):
            v = formant.get_value_at_time(fn, float(t))
            if v and not np.isnan(v) and v > 0:
                values[key].append(float(v))
    return {k: float(np.median(vs)) if vs else 0.0 for k, vs in values.items()}


def analyze_all(audio_path: str, transcription: str = "") -> tuple:
    """
    Single-pass analysis: load WAV once, run pitch + formant together,
    then derive all downstream metrics. ~3× faster than calling each
    function separately because Parselmouth only reads the file once.

    Returns a tuple matching the order expected by _run_praat in main.py:
    (pitch_contour, formants, speech_rate, fluency_score, pitch_stats,
     word_prosody, detected_tone, tone_accuracy, feedback, pause_analysis)
    """
    if parselmouth is None:
        pitch_contour = extract_pitch(audio_path)
        formants = extract_formants(audio_path)
        speech_rate = calculate_speech_rate(audio_path, transcription)
        pitch_stats = get_pitch_statistics(pitch_contour)
        word_prosody = estimate_word_prosody(pitch_contour, transcription)
        pause_analysis = analyze_pauses_and_utterances(audio_path)
        _syllables = sum(1 for c in transcription if "一" <= c <= "鿿")
        fluency_score = analyze_fluency(pitch_contour, speech_rate, pause_analysis, _syllables)
        from chinese_tones import generate_comprehensive_feedback
        detected_tone, tone_accuracy = _aggregate_tone_from_words(word_prosody, pitch_contour)
        feedback = generate_comprehensive_feedback(
            detected_tone, tone_accuracy, speech_rate, fluency_score, pitch_contour,
            word_prosody=word_prosody,
        )
        return (pitch_contour, formants, speech_rate, fluency_score, pitch_stats,
                word_prosody, detected_tone, tone_accuracy, feedback, pause_analysis)

    from chinese_tones import generate_comprehensive_feedback

    sound = _load_sound(audio_path)
    duration = max(float(sound.get_total_duration()), 0.01)

    pitch_contour = _pitch_contour_from_sound(sound)
    formants = _formants_from_sound(sound)

    # Speech rate from char count (fast) or pitch frames (fallback)
    chinese_chars = sum(1 for c in transcription if "一" <= c <= "鿿")
    if chinese_chars > 0:
        speech_rate = float(chinese_chars / duration)
    else:
        speech_rate = float(max(1, round(len(pitch_contour) / 9)) / duration)

    pitch_stats = get_pitch_statistics(pitch_contour)
    word_prosody = estimate_word_prosody(pitch_contour, transcription)
    # Reuse already-loaded sound — avoids a second disk read
    pause_analysis = analyze_pauses_and_utterances(audio_path, _preloaded_sound=sound)
    fluency_score = analyze_fluency(pitch_contour, speech_rate, pause_analysis, chinese_chars)

    detected_tone, tone_accuracy = _aggregate_tone_from_words(word_prosody, pitch_contour)
    feedback = generate_comprehensive_feedback(
        detected_tone, tone_accuracy, speech_rate, fluency_score, pitch_contour,
        word_prosody=word_prosody,
    )

    return (pitch_contour, formants, speech_rate, fluency_score, pitch_stats,
            word_prosody, detected_tone, tone_accuracy, feedback, pause_analysis)


def extract_pitch(
    audio_path: str,
    time_step: float = 0.025,
    pitch_floor: float = 75,
    pitch_ceiling: float = 500,
) -> List[Tuple[float, float]]:
    """Extract voiced pitch samples as (time_seconds, frequency_hz)."""
    if parselmouth is None:
        return _extract_pitch_fallback(audio_path, time_step, pitch_floor, pitch_ceiling)

    sound = _load_sound(audio_path)
    return _pitch_contour_from_sound(sound, time_step, pitch_floor, pitch_ceiling)


def extract_formants(
    audio_path: str,
    max_formant: float = 5500,
    num_formants: int = 5,
) -> Dict[str, float]:
    """Return median F1-F3 values across voiced frames."""
    if parselmouth is None:
        return {"F1": 0.0, "F2": 0.0, "F3": 0.0}

    sound = _load_sound(audio_path)
    return _formants_from_sound(sound, max_formant, num_formants)


def calculate_speech_rate(audio_path: str, transcription: str = "") -> float:
    """
    Estimate syllables per second.

    If a transcription is available, Chinese characters are a good proxy for
    syllables. Otherwise, estimate from voiced pitch frames.
    """
    duration = _audio_duration(audio_path)

    if transcription:
        syllable_count = sum(
            1 for char in transcription if "\u4e00" <= char <= "\u9fff"
        )
        if syllable_count > 0:
            return float(syllable_count / duration)

    voiced_points = extract_pitch(audio_path, time_step=0.02)
    estimated_syllables = max(1, round(len(voiced_points) / 9))
    return float(estimated_syllables / duration)


def analyze_pauses_and_utterances(
    audio_path: str,
    frame_duration: float = 0.03,
    hop_duration: float = 0.01,
    speech_threshold_db: float = -35.0,
    min_utterance_duration: float = 0.12,
    min_pause_duration: float = 0.2,
    merge_gap_duration: float = 0.18,
    _preloaded_sound=None,
) -> Dict:
    """
    Segment the recording into speech utterances and silent pauses.
    Pass _preloaded_sound (a parselmouth.Sound) to avoid a second file read.
    """
    if _preloaded_sound is not None and parselmouth is not None:
        sound = _preloaded_sound
        values = np.asarray(sound.values, dtype=float)
        samples = values.mean(axis=0) if values.ndim == 2 else values.reshape(-1)
        sample_rate = int(round(1.0 / sound.dx))
        duration = float(sound.get_total_duration())
    else:
        samples, sample_rate, duration = _load_mono_audio(audio_path)
    if samples.size == 0 or duration <= 0:
        return _empty_pause_analysis()

    peak = float(np.max(np.abs(samples)))
    if peak <= 0:
        return _empty_pause_analysis(duration)

    samples = samples / peak
    frame_size = max(1, int(sample_rate * frame_duration))
    hop_size = max(1, int(sample_rate * hop_duration))

    frames: List[Tuple[float, float, bool]] = []
    for start in range(0, max(samples.size - frame_size + 1, 1), hop_size):
        frame = samples[start : start + frame_size]
        if frame.size == 0:
            continue
        rms = float(np.sqrt(np.mean(frame**2)))
        db = 20.0 * np.log10(max(rms, 1e-8))
        frame_start = start / sample_rate
        frame_end = min((start + frame_size) / sample_rate, duration)
        frames.append((frame_start, frame_end, db >= speech_threshold_db))

    speech_segments = _merge_boolean_segments(
        frames,
        target_state=True,
        min_duration=min_utterance_duration,
        merge_gap=merge_gap_duration,
    )
    pauses = _pauses_between_utterances(speech_segments, min_pause_duration)

    speaking_time = sum(segment["duration"] for segment in speech_segments)
    total_pause_duration = sum(pause["duration"] for pause in pauses)
    speech_ratio = speaking_time / duration if duration else 0.0

    return {
        "duration": round(duration, 3),
        "utterance_count": len(speech_segments),
        "utterances": speech_segments,
        "pause_count": len(pauses),
        "pauses": pauses,
        "total_speaking_duration": round(speaking_time, 3),
        "total_pause_duration": round(total_pause_duration, 3),
        "longest_pause": round(
            max((pause["duration"] for pause in pauses), default=0.0),
            3,
        ),
        "speech_ratio": round(speech_ratio, 3),
    }


def _load_mono_audio(audio_path: str) -> Tuple[np.ndarray, int, float]:
    if parselmouth is not None:
        sound = _load_sound(audio_path)
        values = np.asarray(sound.values, dtype=float)
        if values.ndim == 2:
            samples = values.mean(axis=0)
        else:
            samples = values.reshape(-1)
        return samples, int(round(1.0 / sound.dx)), float(sound.get_total_duration())

    with wave.open(audio_path, "rb") as wav_file:
        frame_rate = wav_file.getframerate()
        sample_width = wav_file.getsampwidth()
        channels = wav_file.getnchannels()
        frames = wav_file.readframes(wav_file.getnframes())

    if sample_width != 2:
        return np.array([], dtype=float), frame_rate, 0.0

    audio = np.frombuffer(frames, dtype=np.int16).astype(float)
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    duration = audio.size / float(frame_rate) if frame_rate else 0.0
    return audio, frame_rate, duration


def _merge_boolean_segments(
    frames: List[Tuple[float, float, bool]],
    target_state: bool,
    min_duration: float,
    merge_gap: float,
) -> List[Dict]:
    raw_segments: List[Dict] = []
    active_start = None
    active_end = None

    for frame_start, frame_end, state in frames:
        if state == target_state:
            if active_start is None:
                active_start = frame_start
            active_end = frame_end
        elif active_start is not None and active_end is not None:
            raw_segments.append({"start": active_start, "end": active_end})
            active_start = None
            active_end = None

    if active_start is not None and active_end is not None:
        raw_segments.append({"start": active_start, "end": active_end})

    merged: List[Dict] = []
    for segment in raw_segments:
        if not merged or segment["start"] - merged[-1]["end"] > merge_gap:
            merged.append(segment)
        else:
            merged[-1]["end"] = segment["end"]

    cleaned = []
    for index, segment in enumerate(merged):
        duration = segment["end"] - segment["start"]
        if duration >= min_duration:
            cleaned.append(
                {
                    "index": len(cleaned),
                    "start": round(segment["start"], 3),
                    "end": round(segment["end"], 3),
                    "duration": round(duration, 3),
                }
            )
    return cleaned


def _pauses_between_utterances(
    utterances: List[Dict],
    min_pause_duration: float,
) -> List[Dict]:
    pauses: List[Dict] = []
    for previous, current in zip(utterances, utterances[1:]):
        start = float(previous["end"])
        end = float(current["start"])
        duration = end - start
        if duration >= min_pause_duration:
            pauses.append(
                {
                    "index": len(pauses),
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "duration": round(duration, 3),
                }
            )
    return pauses


def _empty_pause_analysis(duration: float = 0.0) -> Dict:
    return {
        "duration": round(duration, 3),
        "utterance_count": 0,
        "utterances": [],
        "pause_count": 0,
        "pauses": [],
        "total_speaking_duration": 0.0,
        "total_pause_duration": 0.0,
        "longest_pause": 0.0,
        "speech_ratio": 0.0,
    }


def _audio_duration(audio_path: str) -> float:
    if parselmouth is not None:
        sound = _load_sound(audio_path)
        return max(sound.get_total_duration(), 0.01)

    try:
        with wave.open(audio_path, "rb") as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            return max(frames / float(rate), 0.01)
    except Exception:
        return 1.0


def _extract_pitch_fallback(
    audio_path: str,
    time_step: float,
    pitch_floor: float,
    pitch_ceiling: float,
) -> List[Tuple[float, float]]:
    """
    Lightweight fallback for local development when Parselmouth is unavailable.

    This estimates voiced pitch from zero crossings in short WAV windows. It is
    not a replacement for Praat, but it keeps the speech-analysis API usable
    until the Docker/Praat backend is available again.
    """
    try:
        with wave.open(audio_path, "rb") as wav_file:
            frame_rate = wav_file.getframerate()
            sample_width = wav_file.getsampwidth()
            channels = wav_file.getnchannels()
            frames = wav_file.readframes(wav_file.getnframes())
    except Exception as exc:
        raise RuntimeError("Could not read WAV audio for fallback analysis.") from exc

    if sample_width != 2:
        return []

    audio = np.frombuffer(frames, dtype=np.int16)
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1).astype(np.int16)

    window_size = max(int(frame_rate * 0.04), 1)
    hop_size = max(int(frame_rate * time_step), 1)
    contour: List[Tuple[float, float]] = []

    for start in range(0, max(len(audio) - window_size, 0), hop_size):
        window = audio[start : start + window_size].astype(float)
        if window.size < 4 or float(np.sqrt(np.mean(window**2))) < 120:
            continue

        centered = window - float(np.mean(window))
        crossings = np.where(np.diff(np.signbit(centered)))[0]
        frequency = (len(crossings) * frame_rate) / (2.0 * window.size)
        if pitch_floor <= frequency <= pitch_ceiling:
            contour.append((float(start / frame_rate), float(frequency)))

    return _correct_octave_jumps(contour)


def analyze_fluency(
    pitch_contour: List[Tuple[float, float]],
    speech_rate: float,
    pause_analysis: Dict | None = None,
    syllable_count: int = 0,
) -> float:
    """Score speaking fluency on a 0-100 scale.

    When pause structure is available, the score is dominated by utterance-
    fluency measures (phonation-time ratio, articulation rate, mean length of
    run; Towell et al. 1996; De Jong et al. 2012) computed in ``caf_metrics``,
    blended with a pitch-continuity term. Falls back to the pitch-continuity
    heuristic alone when no pause data is supplied.
    """
    if len(pitch_contour) < 3:
        return 0.0

    frequencies = np.array([point[1] for point in pitch_contour])
    times = np.array([point[0] for point in pitch_contour])

    pitch_jumps = np.abs(np.diff(frequencies))
    jump_penalty = min(45.0, float(np.mean(pitch_jumps) / 2.5))

    gaps = np.diff(times)
    pause_penalty = min(35.0, float(np.sum(gaps > 0.18) * 7))

    rate_penalty = 0.0
    if speech_rate < 2.5:
        rate_penalty = min(20.0, (2.5 - speech_rate) * 8)
    elif speech_rate > 6.5:
        rate_penalty = min(20.0, (speech_rate - 6.5) * 8)

    continuity = max(0.0, min(100.0, 100.0 - jump_penalty - pause_penalty - rate_penalty))

    if pause_analysis:
        import caf_metrics

        utterance = caf_metrics.fluency_metrics(
            speech_rate, pause_analysis, syllable_count
        )["score"]
        # Weight the literature-grounded utterance fluency above the prosodic
        # continuity term.
        return float(max(0.0, min(100.0, 0.65 * utterance + 0.35 * continuity)))

    return float(continuity)


def get_pitch_statistics(
    pitch_contour: List[Tuple[float, float]]
) -> Dict[str, float]:
    """Summarize the extracted pitch contour."""
    if not pitch_contour:
        return {
            "mean_frequency": 0.0,
            "min_frequency": 0.0,
            "max_frequency": 0.0,
            "frequency_range": 0.0,
        }

    frequencies = np.array([point[1] for point in pitch_contour])
    return {
        "mean_frequency": float(np.mean(frequencies)),
        "min_frequency": float(np.min(frequencies)),
        "max_frequency": float(np.max(frequencies)),
        "frequency_range": float(np.max(frequencies) - np.min(frequencies)),
    }


def _aggregate_tone_from_words(
    word_prosody: List[Dict], pitch_contour: List[Tuple[float, float]]
) -> Tuple[int, float]:
    """Roll per-word phrase-grounded tone scores up into one overall score.

    Replaces the old approach of fitting the *entire* recording's pitch
    contour against a single canonical tone shape — that only made sense for
    isolated single syllables and produced poor scores on real phrases.
    Falls back to the legacy whole-utterance guess when there's no usable
    transcription (e.g. silence, or non-Chinese text).
    """
    scored = [w for w in word_prosody if w.get("expected_tones")]
    if not scored:
        from chinese_tones import detect_tone

        tone_detection = detect_tone(pitch_contour)
        detected_tone = tone_detection["detected_tone"]
        return detected_tone, tone_detection["scores"].get(detected_tone, 0)

    total_weight = sum(len(w["expected_tones"]) for w in scored)
    weighted_accuracy = sum(
        w["tone_accuracy"] * len(w["expected_tones"]) for w in scored
    ) / max(total_weight, 1)

    all_tones = [t for w in scored for t in w["expected_tones"]]
    dominant_tone = max(set(all_tones), key=all_tones.count) if all_tones else 0

    return dominant_tone, round(weighted_accuracy, 1)


def estimate_word_prosody(
    pitch_contour: List[Tuple[float, float]],
    transcription: str = "",
) -> List[Dict]:
    """
    Estimate per-word prosody from the global pitch contour.

    Words (not isolated characters) are the unit: the transcription is
    word-segmented with jieba, and each word's time span \u2014 proportional to
    its character count \u2014 is sliced from the voiced pitch duration. The tone
    score for each word is matched against its *actual* expected tones (via
    pinyin, with third-tone sandhi applied), not a best-fit guess among the
    four canonical single-syllable shapes. This is a lightweight alignment
    approximation, not a replacement for forced alignment.
    """
    tokens = _prosody_tokens(transcription)
    if not tokens or len(pitch_contour) < 2:
        return []

    from chinese_tones import (
        apply_tone_sandhi,
        calculate_phrase_shape_accuracy,
        calculate_phrase_tone_accuracy,
        scaled_reference_contour,
        word_tones,
    )

    start_time = float(pitch_contour[0][0])
    end_time = float(pitch_contour[-1][0])
    duration = max(end_time - start_time, 0.01)
    total_chars = sum(max(len(t), 1) for t in tokens)
    avg_syllable_duration = duration / max(total_chars, 1)
    onset_times = _voicing_onset_times(pitch_contour)
    segments: List[Dict] = []

    cursor = start_time
    for index, token in enumerate(tokens):
        weight = max(len(token), 1) / total_chars
        segment_start = cursor
        proportional_end = segment_start + duration * weight
        if index == len(tokens) - 1:
            segment_end = end_time
        else:
            segment_end = _snap_to_onset(
                proportional_end, onset_times, avg_syllable_duration
            )
        cursor = segment_end

        points = [
            (float(time), float(freq))
            for time, freq in pitch_contour
            if segment_start <= float(time) <= segment_end
        ]

        if not points:
            nearest = min(
                pitch_contour,
                key=lambda point: abs(float(point[0]) - segment_start),
            )
            points = [(float(nearest[0]), float(nearest[1]))]

        frequencies = np.array([point[1] for point in points], dtype=float)
        start_pitch = float(frequencies[0])
        end_pitch = float(frequencies[-1])
        mean_pitch = float(np.mean(frequencies))
        pitch_range = float(np.max(frequencies) - np.min(frequencies))
        slope = end_pitch - start_pitch
        contour_shape = _contour_shape(frequencies, slope, pitch_range)

        is_chinese = bool(re.search(r"[\u4e00-\u9fff]", token))
        expected_tones = apply_tone_sandhi(word_tones(token)) if is_chinese else []

        # Coarticulation onset skip: the first ~12 % of a word's pitch frames
        # often still carry the final pitch direction of the previous word.
        # Skipping this transition window gives a cleaner tone-shape reading
        # without affecting the visual contour or start/end pitch display.
        _ONSET_SKIP = 0.12
        onset_threshold = segment_start + (segment_end - segment_start) * _ONSET_SKIP
        scoring_points = [p for p in points if p[0] >= onset_threshold] or points

        # Need ≥4 pitch points for a reliable tone shape read. Fewer points
        # (e.g. from a voicing gap at a word boundary) return a neutral 65 so
        # a single unvoiced frame doesn't collapse the whole word score to 0.
        #
        # tone_score (declination-robust, direction-weighted) drives the
        # numeric tone_accuracy used for aggregation/gating — unchanged here.
        # shape_score is a *separate*, pure shape-similarity read used only
        # for this word's feedback text, because the card shown to the
        # student overlays "your pitch" directly against "target shape" —
        # the feedback should track that same visual comparison, not the
        # directional blend (which can score a shape with the right broad
        # direction but the wrong internal contour, e.g. a dip performed as
        # a rise-then-dip in the wrong order, deceptively close to "good").
        if is_chinese and len(scoring_points) >= 4:
            tone_score = calculate_phrase_tone_accuracy(scoring_points, expected_tones)
            shape_score = calculate_phrase_shape_accuracy(scoring_points, expected_tones)
        elif is_chinese and expected_tones:
            tone_score = 65.0
            shape_score = 65.0
        else:
            tone_score = 0.0
            shape_score = 0.0
        is_content = _classify_content_word(token)

        # Idealized target shape for this word, scaled to its own time span
        # and pitch range so the frontend can overlay "your pitch" against
        # "target shape" directly — the visual answer to "how do I fix this?"
        reference_contour = (
            scaled_reference_contour(
                expected_tones, segment_start, segment_end,
                float(np.min(frequencies)), float(np.max(frequencies)),
            )
            if is_chinese and expected_tones
            else []
        )

        segments.append(
            {
                "token": token,
                "index": index,
                "start_time": round(segment_start, 3),
                "end_time": round(segment_end, 3),
                "pitch_contour": points,
                "reference_contour": reference_contour,
                "mean_pitch": round(mean_pitch, 2),
                "pitch_range": round(pitch_range, 2),
                "start_pitch": round(start_pitch, 2),
                "end_pitch": round(end_pitch, 2),
                "contour_shape": contour_shape,
                "expected_tones": expected_tones,
                "tone_accuracy": round(tone_score, 1),
                "is_content_word": is_content,
                "prominence_score": 0.0,  # filled in below after utterance mean is known
                "feedback": _word_prosody_feedback(contour_shape, pitch_range, expected_tones, shape_score),
            }
        )

    # Compute prominence_score relative to utterance mean pitch
    all_pitches = [s["mean_pitch"] for s in segments if s["mean_pitch"] > 0]
    utterance_mean = float(np.mean(all_pitches)) if all_pitches else 0.0
    if utterance_mean > 0:
        for seg in segments:
            seg["prominence_score"] = round(
                (seg["mean_pitch"] - utterance_mean) / utterance_mean, 3
            )

    return segments


def _voicing_onset_times(
    pitch_contour: List[Tuple[float, float]],
    gap_threshold: float = 0.06,
) -> List[float]:
    """Find times where voicing resumes after a brief gap.

    The voiced pitch contour already excludes unvoiced frames, so a gap
    between consecutive points longer than ``gap_threshold`` marks a likely
    syllable or word boundary (a stop consonant, glottal break, or brief
    pause). These onsets are real acoustic landmarks, unlike the purely
    proportional character-count split used as the initial boundary guess.
    """
    if len(pitch_contour) < 2:
        return []

    onsets: List[float] = []
    for i in range(1, len(pitch_contour)):
        prev_time = float(pitch_contour[i - 1][0])
        cur_time = float(pitch_contour[i][0])
        if cur_time - prev_time > gap_threshold:
            onsets.append(cur_time)
    return onsets


def _snap_to_onset(
    proportional_time: float,
    onset_times: List[float],
    avg_syllable_duration: float,
) -> float:
    """Move a proportionally-guessed boundary to the nearest real onset.

    Only snaps within half a syllable's duration of the guess, so a stray
    onset from a different part of the phrase can't pull a boundary far from
    where the character-count estimate placed it.
    """
    if not onset_times:
        return proportional_time

    tolerance = max(avg_syllable_duration / 2.0, 0.03)
    nearest = min(onset_times, key=lambda t: abs(t - proportional_time))
    if abs(nearest - proportional_time) <= tolerance:
        return nearest
    return proportional_time


_CONTENT_POS_PREFIXES = frozenset({"n", "v", "a", "t", "s", "i"})


def _classify_content_word(token: str) -> bool:
    """True when a jieba token carries lexical (not grammatical) content.

    POS prefix key: n=noun, v=verb, a=adjective, t=time noun, s=location noun,
    i=idiom. Function words (r=pronoun, p=prep, c=conj, u=particle, y=modal,
    e=exclamation, q=classifier, m=numeral) are treated as unstressed.
    """
    if not re.search(r"[一-鿿]", token):
        return False
    try:
        import jieba.posseg as pseg
        for _, flag in pseg.cut(token):
            return flag[:1] in _CONTENT_POS_PREFIXES
    except Exception:
        pass
    return True  # no POS tagging available → assume content


def word_stress_summary(word_prosody: List[Dict]) -> Dict:
    """Derive a sentence-level stress / topline summary from per-word segments.

    Returns:
      content_word_count: int
      de_accented_words: List[str]  — content words whose pitch sat below average
      prominent_words: List[str]    — content words with clearly elevated pitch
      topline_slope_hz_per_sec: float  — negative = natural declination
    """
    if not word_prosody:
        return {}

    content_words = [w for w in word_prosody if w.get("is_content_word")]
    de_accented = [w["token"] for w in content_words if w.get("prominence_score", 0) < -0.12]
    prominent = [w["token"] for w in content_words if w.get("prominence_score", 0) > 0.10]

    topline_slope = 0.0
    if len(content_words) >= 2:
        times = np.array([w["start_time"] for w in content_words], dtype=float)
        peaks = np.array([w.get("start_pitch", w["mean_pitch"]) for w in content_words], dtype=float)
        valid = peaks > 0
        if valid.sum() >= 2:
            t, p = times[valid], peaks[valid]
            denom = float(((t - t.mean()) ** 2).sum())
            if denom > 0:
                topline_slope = float(((t - t.mean()) * (p - p.mean())).sum() / denom)

    return {
        "content_word_count": len(content_words),
        "de_accented_words": de_accented,
        "prominent_words": prominent,
        "topline_slope_hz_per_sec": round(topline_slope, 1),
    }


def _prosody_tokens(transcription: str) -> List[str]:
    text = transcription.strip()
    if not text:
        return []

    if re.search(r"[\u4e00-\u9fff]", text):
        from caf_metrics import segment_words

        words = segment_words(text)
        # Cap at 80 characters total (not 80 words) to match the old budget.
        capped: List[str] = []
        char_budget = 80
        for word in words:
            if char_budget <= 0:
                break
            capped.append(word)
            char_budget -= len(word)
        return capped

    return re.findall(r"[A-Za-z0-9']+", text)[:40]


def _contour_shape(frequencies: np.ndarray, slope: float, pitch_range: float) -> str:
    if len(frequencies) >= 3:
        middle = float(frequencies[len(frequencies) // 2])
        if middle < float(frequencies[0]) and middle < float(frequencies[-1]):
            return "dip"

    if pitch_range < 18:
        return "level"
    if slope > 12:
        return "rising"
    if slope < -12:
        return "falling"
    return "variable"


_TONE_NAMES = {1: "Tone 1 (level)", 2: "Tone 2 (rising)", 3: "Tone 3 (dip)", 4: "Tone 4 (falling)", 5: "neutral tone"}


def _word_prosody_feedback(
    contour_shape: str,
    pitch_range: float,
    expected_tones: List[int] | None = None,
    shape_score: float = 0.0,
) -> str:
    """`shape_score` should be a pure shape-similarity score (e.g.
    ``calculate_phrase_shape_accuracy``), not the direction-weighted
    ``tone_accuracy`` blend — this text is paired with a chart that overlays
    the student's pitch directly against the idealized target shape, so it
    needs to agree with that same shape comparison, not a declination-robust
    score that can rate a wrong-shaped-but-right-direction attempt as "good"."""
    if expected_tones:
        tone_label = "+".join(_TONE_NAMES.get(t, str(t)) for t in expected_tones)
        if shape_score >= 68:
            return f"Good match for {tone_label}."
        if shape_score >= 48:
            return f"Recognizable {tone_label}, but contrast could be sharper."
        return f"Expected {tone_label} — pitch shape doesn't match yet."

    if contour_shape == "level":
        return "Stable pitch. Good for level or unstressed syllables."
    if contour_shape == "rising":
        return "Pitch rises clearly."
    if contour_shape == "falling":
        return "Pitch falls clearly."
    if contour_shape == "dip":
        return "Pitch dips in the middle."
    if pitch_range > 80:
        return "Large pitch movement; check whether it matches the intended tone."
    return "Some pitch movement is present; try making the tone shape clearer."
