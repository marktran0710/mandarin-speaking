"""
Praat acoustic analysis helpers powered by Parselmouth.

Parselmouth embeds Praat's analysis routines in Python, so the API can extract
pitch and formant features without shelling out to the Praat desktop app.
"""
import os
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


# Praat's own default step for a 75 Hz floor is 0.75 / 75 = 10 ms. The previous
# 25 ms yielded only ~6-7 voiced frames per Mandarin syllable, which is too few
# to read a tone contour: the quarter-means used for start and end pitch
# collapsed to a single frame each, so a measured "slope" was one noisy frame
# minus another. On native speakers -- who produce tones correctly by
# definition -- that made rising tone 2 measure at +0.11 st, indistinguishable
# from level tone 1 at +0.02 st. See scripts/validate_tone_measurement.py.
PITCH_TIME_STEP = 0.010


def _pitch_contour_from_sound(
    sound,
    time_step: float = PITCH_TIME_STEP,
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
    time_step: float = 0.025,
) -> Dict[str, float]:
    """Return median F1-F3 using Parselmouth's native time grid (avoids 360 Python calls).

    ``time_step`` is exposed so a caller measuring a single syllable's vowel —
    a slice tens of milliseconds long — can ask for a finer grid; the default
    is tuned for whole-utterance analysis where 25 ms is plenty.
    """
    formant = sound.to_formant_burg(
        time_step=time_step,
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


def analyze_all(
    audio_path: str,
    transcription: str = "",
    pinyin_hint: str = "",
    reference_word_curves: Dict[str, List[float]] | None = None,
) -> tuple:
    """
    Single-pass analysis: load WAV once, run pitch + formant together,
    then derive all downstream metrics. ~3× faster than calling each
    function separately because Parselmouth only reads the file once.

    ``pinyin_hint``, when given, is the caller's own tone-marked pinyin for
    ``transcription`` (e.g. a vocabulary word's displayed/teacher-corrected
    pinyin) — used to derive expected tones directly instead of a second,
    independent pypinyin lookup on the characters. See
    ``estimate_word_prosody`` for how it's applied.

    ``reference_word_curves``, when given, is passed straight through to
    ``estimate_word_prosody`` so scene words with a cached model-voice clip
    are scored/charted against that real recording. See that function.

    Returns a tuple matching the order expected by _run_praat in main.py:
    (pitch_contour, formants, speech_rate, fluency_score, pitch_stats,
     word_prosody, detected_tone, tone_accuracy, feedback, pause_analysis)
    """
    if parselmouth is None:
        pitch_contour = extract_pitch(audio_path)
        formants = extract_formants(audio_path)
        speech_rate = calculate_speech_rate(audio_path, transcription)
        pitch_stats = get_pitch_statistics(pitch_contour)
        word_prosody = estimate_word_prosody(
            pitch_contour, transcription, pinyin_hint=pinyin_hint,
            reference_word_curves=reference_word_curves,
        )
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
    word_prosody = estimate_word_prosody(
        pitch_contour, transcription, pinyin_hint=pinyin_hint,
        reference_word_curves=reference_word_curves,
        intensity=_intensity_contour_from_sound(sound),
        sound=sound,
    )
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
    time_step: float = PITCH_TIME_STEP,
    pitch_floor: float = 75,
    pitch_ceiling: float = 500,
) -> List[Tuple[float, float]]:
    """Extract voiced pitch samples as (time_seconds, frequency_hz)."""
    if parselmouth is None:
        return _extract_pitch_fallback(audio_path, time_step, pitch_floor, pitch_ceiling)

    sound = _load_sound(audio_path)
    return _pitch_contour_from_sound(sound, time_step, pitch_floor, pitch_ceiling)


def _intensity_contour_from_sound(sound) -> List[Tuple[float, float]]:
    """Frame-wise intensity (dB) used to locate syllable nuclei.

    Syllable nuclei are intensity peaks, so the valleys between them mark
    boundaries — the only cue available when two syllables run together with
    no break in voicing. Failure is non-fatal: alignment then falls back to
    voicing gaps alone rather than losing the whole analysis.
    """
    try:
        intensity = sound.to_intensity()
        values = intensity.values[0]
        times = [float(intensity.xs()[i]) for i in range(len(values))]
        return [
            (time, float(value))
            for time, value in zip(times, values)
            if np.isfinite(value)
        ]
    except Exception:
        return []


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
    scored = [
        w for w in word_prosody
        if w.get("expected_tones") and w.get("judged", True)
    ]
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


# A syllable "passes" when its directional score clears this bar — the same
# 58-point boundary generate_phrase_tone_feedback already treats as "needs
# the clearest work". The word-level pass verdict is the MINIMUM syllable
# score (see estimate_word_prosody), so one wrong-direction syllable fails
# the word even when the whole-word average looks fine.
SYLLABLE_PASS_THRESHOLD = 58.0


def _aligner():
    """The configured syllable aligner.

    Selected by TONE_ALIGNER so the OMPAL benchmark can measure the old
    proportional split against the new one without a code change, which is
    what makes the improvement attributable rather than merely asserted.
    """
    from tone_scoring.alignment import get_aligner

    return get_aligner(os.getenv("TONE_ALIGNER", "energy"))


def _windows_for_spans(
    points: List[Tuple[float, float]], spans
) -> List[Tuple[int, int]] | None:
    """Convert syllable time spans into index ranges over ``points``.

    Returns None if any syllable ends up with no frames, so the caller falls
    back to the equal split rather than scoring a tone against nothing.
    """
    windows: List[Tuple[int, int]] = []
    for span in spans:
        start = next(
            (i for i, (time, _) in enumerate(points) if time >= span.start), None
        )
        if start is None:
            return None
        end = start
        for index in range(start, len(points)):
            if points[index][0] > span.end:
                break
            end = index + 1
        if end <= start:
            return None
        windows.append((start, end))
    return windows


# The vowel reading is taken from the middle of the syllable, not all of it.
# The edges carry the initial's formant transitions and the release into the
# next syllable, both of which pull F1/F2 away from the vowel the student
# actually held — measuring them would report the consonant as if it were the
# vowel.
_NUCLEUS_WINDOW = 0.6
# Below this the nucleus is too short to give the formant tracker anything to
# work with, so the syllable reports no formants rather than a noisy guess.
_MIN_NUCLEUS_SECONDS = 0.045


def _nucleus_formants(sound, start: float, end: float) -> Dict[str, float]:
    """Median F1/F2/F3 across the steady middle of one syllable's audio."""
    total = float(sound.get_total_duration())
    start = max(0.0, min(float(start), total))
    end = max(0.0, min(float(end), total))
    span = end - start
    if span <= 0:
        return {"F1": 0.0, "F2": 0.0, "F3": 0.0}
    margin = span * (1.0 - _NUCLEUS_WINDOW) / 2.0
    nucleus_start = start + margin
    nucleus_end = end - margin
    if nucleus_end - nucleus_start < _MIN_NUCLEUS_SECONDS:
        return {"F1": 0.0, "F2": 0.0, "F3": 0.0}
    try:
        slice_sound = sound.extract_part(
            from_time=nucleus_start, to_time=nucleus_end, preserve_times=True
        )
        return _formants_from_sound(slice_sound, time_step=0.01)
    except Exception:
        # A slice Praat refuses (too short for the analysis window, all
        # silence) is missing data, not a reason to fail the whole analysis.
        return {"F1": 0.0, "F2": 0.0, "F3": 0.0}


def _syllable_vowels(sound, spans, tokens: List[str]) -> List[Dict]:
    """Measure every aligned syllable's vowel from its own slice of the audio.

    Returns one record per aligned syllable, in the same order as ``spans``.
    Two passes: measure everything first, because the articulatory reading is
    expressed relative to this recording's own centre and that centre is not
    known until every syllable has been measured.

    No record carries a right/wrong verdict — see ``vowel_analysis`` for why
    a short utterance cannot support one honestly.
    """
    from chinese_tones import syllable_parts, word_tones
    from vowel_analysis import (
        NOT_APPLICABLE,
        NO_FORMANTS,
        expected_vowel,
        is_plausible,
        vowel_zone,
    )

    records: List[Dict] = []
    for token in tokens:
        token_chars = max(len(token), 1)
        is_chinese = bool(re.search(r"[一-鿿]", token))
        parts = syllable_parts(token) if is_chinese else []
        # Dictionary tone, not the sandhi-adjusted one: neutral is a property
        # of the word, and sandhi never creates or removes it.
        tones = word_tones(token) if is_chinese else []
        for offset in range(token_chars):
            initial, final = parts[offset] if offset < len(parts) else ("", "")
            neutral = offset < len(tones) and tones[offset] == 5
            vowel, zone, ceiling = expected_vowel(initial, final, neutral=neutral)
            records.append(
                {
                    "expected_vowel": vowel,
                    "expected_zone": zone,
                    "final": final or None,
                    "ceiling": ceiling,
                    "f1": 0.0,
                    "f2": 0.0,
                }
            )

    for index, record in enumerate(records):
        if record["ceiling"] == NOT_APPLICABLE or index >= len(spans):
            continue
        span = spans[index]
        formants = _nucleus_formants(sound, span.start, span.end)
        f1 = round(float(formants.get("F1", 0.0)), 1)
        f2 = round(float(formants.get("F2", 0.0)), 1)
        # Discard tracker failures here, before they reach the speaker
        # reference below — one 1754 Hz "F1" would otherwise both be shown as
        # fact and skew every other syllable's relative reading.
        if is_plausible(f1, f2):
            record["f1"] = f1
            record["f2"] = f2

    # This recording's own vowel centre — the yardstick every per-syllable
    # reading is expressed against, so the description holds for any voice.
    measured = [(r["f1"], r["f2"]) for r in records if r["f1"] > 0 and r["f2"] > 0]
    reference = (
        (
            float(np.median([f1 for f1, _ in measured])),
            float(np.median([f2 for _, f2 in measured])),
        )
        if measured
        else None
    )

    results: List[Dict] = []
    for record in records:
        f1, f2 = record["f1"], record["f2"]
        status = record["ceiling"]
        if status != NOT_APPLICABLE and (f1 <= 0 or f2 <= 0):
            status = NO_FORMANTS
        results.append(
            {
                "expected_vowel": record["expected_vowel"],
                "expected_zone": record["expected_zone"],
                "final": record["final"],
                "f1": f1,
                "f2": f2,
                "measured_zone": (
                    vowel_zone(f1, f2, reference)
                    if status != NOT_APPLICABLE
                    else None
                ),
                "vowel_status": status,
            }
        )
    return results


def _contextual_tone_plan(
    tokens: List[str], hint_tones: List[int] | None, transcription: str = ""
):
    """Accepted surface tones for every Chinese character in the utterance.

    Isolated behind a try/except because this is a diagnostic add-on: if the
    contextual layer ever raises, the legacy scoring and progression path must
    still return a result. A missing plan degrades the diagnostics to
    "unknown", never the student's score.
    """
    try:
        from tone_context import plan_for_tokens

        # The raw transcript carries the punctuation that segmentation drops,
        # and third-tone sandhi must not cross it.
        return plan_for_tokens(tokens, hint_tones, text=transcription)
    except Exception:  # pragma: no cover - defensive, diagnostics are optional
        return []


def _word_diagnostic_status(syllables: List[Dict]) -> str | None:
    """Roll a word's syllable diagnoses up. None when nothing was diagnosed."""
    from tone_decision import DiagnosticStatus, aggregate_word

    statuses = [
        DiagnosticStatus(entry["diagnostic_status"])
        for entry in syllables
        if entry.get("diagnostic_status")
    ]
    if not statuses:
        return None
    return aggregate_word(statuses).value


def _diagnose_token(
    scoring_points: List[Tuple[float, float]],
    windows: List[Tuple[int, int]] | None,
    expected: List["object"],
    qc_kwargs: Dict,
    score_overrides: List[float] | None = None,
    provenance_overrides: List[str] | None = None,
) -> List[Dict]:
    """Diagnose every syllable of one word against its contextual targets.

    Scored a whole token at a time, not syllable by syllable, because the
    scorer's equal-split fallback derives each syllable's frame range from how
    many syllables it was given. Handing it one syllable at a time made that
    fallback treat the entire word as a single syllable, so every syllable in
    the word came back with the same score — 這 and 個 both reading 100 was
    how that surfaced.
    """
    from chinese_tones import contextual_tone_scores
    from tone_decision import PROVENANCE_NONE, QcEvidence, decide_tone

    evidence = QcEvidence(**qc_kwargs)
    scored = contextual_tone_scores(
        scoring_points,
        [tuple(item.accepted_surface_tones) for item in expected],
        windows,
    )

    results: List[Dict] = []
    for index, item in enumerate(expected):
        if score_overrides and index < len(score_overrides):
            score = score_overrides[index]
            provenance = (
                provenance_overrides[index]
                if provenance_overrides and index < len(provenance_overrides)
                else "reference_shape"
            )
            matched_tone = (
                item.accepted_surface_tones[0]
                if item.accepted_surface_tones
                else None
            )
        elif index < len(scored):
            score, matched_tone, provenance = scored[index]
        else:
            score, matched_tone, provenance = None, None, PROVENANCE_NONE

        diagnosis = decide_tone(
            score,
            provenance,
            evidence,
            matched_surface_tone=matched_tone,
            measurable_by_contour=item.measurable_by_contour,
        )
        record = diagnosis.as_dict()
        record.update(
            {
                "underlying_tone": item.underlying_tone,
                "accepted_surface_tones": list(item.accepted_surface_tones),
                "tone_realization": item.realization,
                "context_rule": item.rule,
                "token_index": item.token_index,
                "boundary_before": item.boundary_before,
                "boundary_after": item.boundary_after,
            }
        )
        results.append(record)
    return results


def estimate_word_prosody(
    pitch_contour: List[Tuple[float, float]],
    transcription: str = "",
    pinyin_hint: str = "",
    reference_word_curves: Dict[str, List[float]] | None = None,
    intensity: List[Tuple[float, float]] | None = None,
    sound=None,
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

    ``pinyin_hint``: the caller's own tone-marked pinyin for the whole
    ``transcription`` (space-separated per syllable, e.g. "ji\u011b jie"). When
    its syllable count matches the transcription's hanzi character count,
    those tones are used directly instead of an independent pypinyin lookup
    on the characters \u2014 so the scored/displayed target shape can never
    silently disagree with whatever pinyin the student or teacher is
    actually looking at (e.g. a teacher's manually corrected vocabulary
    pinyin, or a polyphonic character pypinyin reads differently out of
    context). Falls back to the pypinyin lookup when absent or mismatched.

    ``reference_word_curves``: an optional {word: 100-point [0,1] shape
    curve} map \u2014 the cached model-voice reference generated for this scene
    (see ``reference_curve_for_span``). A token that exactly matches one of
    these keys is scored and charted against that real recording instead of
    the synthetic idealized tone-shape pattern; tokens with no match (e.g.
    function words never given a model-voice clip) keep the synthetic
    fallback so the whole scoring path never depends on every token having
    a reference clip.

    ``sound``: the already-loaded Parselmouth Sound for this recording. When
    given (and the aligner produced one span per syllable), each syllable also
    carries a real F1/F2 reading measured from its own audio — see
    ``_syllable_vowels`` for what that reading is and is not allowed to claim.
    Omitted, every syllable reports ``vowel_status: "not_measured"``, which is
    what the no-Parselmouth fallback path and the existing callers get.
    """
    tokens = _prosody_tokens(transcription)
    if not tokens or len(pitch_contour) < 2:
        return []

    from chinese_tones import (
        apply_tone_sandhi,
        calculate_directional_tone_accuracy,
        calculate_phrase_shape_accuracy,
        calculate_phrase_tone_accuracy,
        directional_tone_scores,
        parse_pinyin_tones,
        phrase_shape_curves,
        reference_syllable_scores,
        scaled_reference_contour,
        word_tones,
    )
    from tone_decision import (
        DiagnosticStatus,
        QcEvidence,
        aggregate_word,
        decide_word_tone,
    )

    hint_tones = parse_pinyin_tones(pinyin_hint) if pinyin_hint else []
    total_hanzi_chars = sum(
        len(t) for t in tokens if re.search(r"[\u4e00-\u9fff]", t)
    )
    use_hint = bool(hint_tones) and len(hint_tones) == total_hanzi_chars
    hint_cursor = 0

    start_time = float(pitch_contour[0][0])
    end_time = float(pitch_contour[-1][0])
    duration = max(end_time - start_time, 0.01)
    total_chars = sum(max(len(t), 1) for t in tokens)
    avg_syllable_duration = duration / max(total_chars, 1)
    onset_times = _voicing_onset_times(pitch_contour)
    segments: List[Dict] = []

    # Syllable boundaries come from the configured aligner. The transcript is
    # known, so the syllable count is an exact constraint rather than a guess;
    # word spans are then just runs of those syllables. The old proportional
    # split is still reachable by configuration so it can act as the ablation
    # control (see tone_scoring.alignment).
    syllable_spans = _aligner().align(pitch_contour, total_chars, intensity)
    use_spans = len(syllable_spans) == total_chars

    # The vowel readout rides on the same syllable boundaries the tone scores
    # use. Without audio, or without one span per syllable, there is nothing
    # real to measure and every syllable says so rather than guessing.
    vowel_records: List[Dict] | None = (
        _syllable_vowels(sound, syllable_spans, tokens)
        if sound is not None and use_spans
        else None
    )

    # Contextual tone plan for the WHOLE utterance. Built here rather than per
    # token because third-tone sandhi crosses word boundaries — 很好 is two
    # jieba tokens, so the per-token `apply_tone_sandhi` below never sees the
    # T3+T3 pair and scores 很 against a full dipping template it should not
    # have. This plan is diagnostic-only; the legacy `expected_tones` computed
    # inside the loop is untouched, so progression cannot shift.
    tone_plan = _contextual_tone_plan(
        tokens, hint_tones if use_hint else None, transcription
    )

    cursor = start_time
    consumed = 0
    for index, token in enumerate(tokens):
        token_chars = max(len(token), 1)
        weight = token_chars / total_chars
        segment_start = cursor
        if use_spans:
            span_slice = syllable_spans[consumed : consumed + token_chars]
            segment_start = span_slice[0].start if span_slice else cursor
            segment_end = span_slice[-1].end if span_slice else end_time
        elif index == len(tokens) - 1:
            segment_end = end_time
        else:
            segment_end = _snap_to_onset(
                segment_start + duration * weight,
                onset_times,
                avg_syllable_duration,
            )
        consumed += token_chars
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
        if is_chinese and use_hint:
            token_tones = hint_tones[hint_cursor : hint_cursor + len(token)]
            hint_cursor += len(token)
        else:
            token_tones = word_tones(token) if is_chinese else []
        expected_tones = apply_tone_sandhi(token_tones) if is_chinese else []

        # Coarticulation onset skip: the first ~12 % of a word's pitch frames
        # often still carry the final pitch direction of the previous word.
        # Skipping this transition window gives a cleaner tone-shape reading
        # without affecting the visual contour or start/end pitch display.
        _ONSET_SKIP = 0.12
        onset_threshold = segment_start + (segment_end - segment_start) * _ONSET_SKIP
        scoring_points = [p for p in points if p[0] >= onset_threshold] or points

        # Need ≥4 pitch points for a reliable tone shape read. Fewer points
        # (e.g. from a voicing gap at a word boundary) are unjudged instead
        # of receiving a fabricated neutral score.
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
        # user_curve/target_curve are the *same normalized arrays* the shape
        # score compares (see phrase_shape_curves) — returned so the frontend
        # chart draws exactly what was scored. Empty when the segment was too
        # short to score, in which case the card falls back to raw Hz.
        reference_curve = _reference_curve_for_token(token, reference_word_curves)

        user_curve: List[float] = []
        target_curve: List[float] = []
        syllable_scores: List[float] = []
        syllable_score_provenance: List[str] = []
        windows: List[Tuple[int, int]] | None = None
        minimum_points = max(4, len(expected_tones) * 4)
        segment_judged = (
            is_chinese
            and bool(expected_tones)
            and len(scoring_points) >= minimum_points
        )
        # `direction_score` is measured separately from `shape_score` so
        # the word-level verdict can require BOTH (via decide_word_tone) —
        # the old 50/50 blend collapsed them into one number that let a
        # weak directional heuristic veto a visibly-correct shape, and vice
        # versa. Keep them apart end-to-end.
        direction_score = 0.0
        if segment_judged:
            tone_score = calculate_phrase_tone_accuracy(
                scoring_points, expected_tones, target_curve_override=reference_curve
            )
            shape_score = calculate_phrase_shape_accuracy(
                scoring_points, expected_tones, target_curve_override=reference_curve
            )
            user_curve, target_curve = phrase_shape_curves(
                scoring_points, expected_tones, target_curve_override=reference_curve
            )
            # Hand the scorer this word's real per-syllable boundaries so each
            # tone template is matched against its own audio, instead of an
            # equal share of the word's frames.
            if use_spans:
                spans = syllable_spans[consumed - token_chars : consumed]
                if len(spans) == len(expected_tones):
                    windows = _windows_for_spans(scoring_points, spans)
            if reference_curve:
                syllable_scores, syllable_score_provenance = reference_syllable_scores(
                    scoring_points,
                    expected_tones,
                    reference_curve,
                    syllable_windows=windows,
                )
                # With a real reference curve, syllable scores ARE the
                # reference-shape read; treat their mean as the word's
                # direction-of-fit signal so the two verdict inputs both
                # exist without introducing a second directional measure
                # against a synthetic template.
                direction_score = (
                    float(np.mean(syllable_scores)) if syllable_scores else 0.0
                )
            else:
                syllable_scores = directional_tone_scores(
                    scoring_points, expected_tones, syllable_windows=windows
                )
                direction_score = calculate_directional_tone_accuracy(
                    scoring_points, expected_tones
                )
        elif is_chinese and expected_tones:
            tone_score = 0.0
            shape_score = 0.0
            # Keep shape fields numeric for API compatibility, but mark the
            # syllables and word unjudged below.
            syllable_scores = [0.0] * len(expected_tones)
        else:
            tone_score = 0.0
            shape_score = 0.0
        is_content = _classify_content_word(token)

        # Per-syllable breakdown + pass verdict. The word-level scores above
        # average across syllables, which lets a clean second syllable mask a
        # wrong-direction first one (e.g. 在 said rising in 在家) — so the
        # pass gate is the *minimum* syllable score, not the mean. One entry
        # per character; empty for non-Chinese tokens. `passed` is None for
        # non-Chinese tokens (nothing to gate on).
        # Per-syllable breakdown. `passed` is filled in below from the
        # diagnostic verdict (passed = verdict == CORRECT) so the legacy
        # placeholder auto-pass (constant 65/75 clearing the 58 bar) can no
        # longer produce True. `legacy_passed` (below) preserves the old
        # threshold-only verdict for research/backwards compat.
        syllables: List[Dict] = []
        if is_chinese and syllable_scores and len(expected_tones) == len(token):
            syllables = [
                {
                    "char": token[i],
                    "tone": expected_tones[i],
                    "score": round(score, 1),
                    # Filled in by the diagnostic wiring below. None when the
                    # segment could not be judged at all.
                    "passed": None,
                }
                for i, score in enumerate(syllable_scores)
            ]
            # The vowel reading is a measurement shown next to the tone, not a
            # second score. It never touches `passed`: the mastery gate stays
            # a tone gate.
            for i, entry in enumerate(syllables):
                record = None
                if vowel_records is not None:
                    global_index = consumed - token_chars + i
                    if 0 <= global_index < len(vowel_records):
                        record = vowel_records[global_index]
                entry.update(record or {"vowel_status": "not_measured"})

            # ── Diagnostic layer, strictly parallel to the legacy verdict ──
            # `score` and `passed` above are what progression runs on and are
            # not touched here. These fields answer a different question:
            # given the tone this syllable is *allowed* to surface as in this
            # context, and given whether the measurement can be trusted at
            # all, what can honestly be said? A weak contour match with thin
            # pitch evidence becomes UNCERTAIN, not a learner error.
            plan_slice = tone_plan[consumed - token_chars : consumed]
            diagnoses = (
                _diagnose_token(
                    scoring_points,
                    windows,
                    plan_slice,
                    {
                        "can_score_pronunciation": True,
                        "judged": segment_judged,
                        "pitch_points": len(scoring_points),
                        "minimum_pitch_points": minimum_points,
                    },
                    score_overrides=(
                        syllable_scores if reference_curve else None
                    ),
                    provenance_overrides=(
                        syllable_score_provenance if reference_curve else None
                    ),
                )
                if len(plan_slice) == len(syllables)
                else []
            )
            for i, entry in enumerate(syllables):
                # Preserve the legacy raw-threshold verdict alongside the
                # canonical one, so research exports and A/B ablation can
                # still see what the old gate would have said without any
                # consumer having to re-derive it.
                score = entry.get("score")
                entry["legacy"] = {
                    "passed": (
                        bool(score >= SYLLABLE_PASS_THRESHOLD)
                        if score is not None and segment_judged
                        else None
                    ),
                    "score": score,
                    "threshold": SYLLABLE_PASS_THRESHOLD,
                }
                if i < len(diagnoses):
                    entry.update(diagnoses[i])
                # The canonical per-syllable pass gate is now the diagnostic
                # verdict: only CORRECT is a pass. UNCERTAIN and INCORRECT
                # both fail, which closes the placeholder-auto-pass loophole
                # (constant_short_segment=65 and neutral_not_measured=75
                # correctly resolve to UNCERTAIN in decide_tone, so passed
                # can never come back True on evidence that wasn't measured).
                #
                # `segment_judged=False` keeps `passed=None` — "nothing to
                # gate on" is not a failure, and downstream mastery counts
                # only judged syllables anyway.
                diagnostic_status = entry.get("diagnostic_status")
                if not segment_judged:
                    entry["passed"] = None
                elif diagnostic_status:
                    entry["passed"] = diagnostic_status == DiagnosticStatus.CORRECT.value
                else:
                    entry["passed"] = entry["legacy"]["passed"]
        # Word verdict: worst of (word-level shape+direction decision,
        # syllable roll-up). The word-level decision catches disagreement
        # between shape and direction as UNCERTAIN; the syllable roll-up
        # keeps the min-rule safety net so one wrong syllable still fails
        # the word even if the overall shape+direction happen to agree.
        word_qc = QcEvidence(
            can_score_pronunciation=True,
            judged=segment_judged,
            pitch_points=len(scoring_points),
            minimum_pitch_points=minimum_points,
        )
        word_decision = decide_word_tone(
            shape_score=shape_score if segment_judged else None,
            direction_score=direction_score if segment_judged else None,
            qc=word_qc,
        )
        syllable_statuses = [
            DiagnosticStatus(entry["diagnostic_status"])
            for entry in syllables
            if entry.get("diagnostic_status")
        ]
        syllable_rollup = (
            aggregate_word(syllable_statuses) if syllable_statuses else None
        )
        # Word-level and syllable-level evidence combine two ways:
        #
        # * word-level shape+direction can promote a word to CORRECT when
        #   the per-syllable directional single-score falls into the
        #   45-58 UNCERTAIN band on every syllable — that band is common in
        #   connected speech (the coarse quarter-mean heuristic dips) and
        #   the whole-word shape/direction match is stronger evidence than
        #   per-syllable ambiguity;
        # * syllable-level CORRECT can promote a word whose whole-word
        #   shape barely missed SHAPE_STRONG (weak_shape reason);
        # * neither promotion is allowed to overrule an INCORRECT syllable
        #   (the min-rule safety net stays intact), a placeholder-driven
        #   UNCERTAIN (short segment / neutral tone — no measurement to
        #   promote from), or a shape/direction disagreement (the whole
        #   point of the refactor's word-level check).
        placeholder_provenances = {
            "constant_short_segment",
            "neutral_not_measured",
            "not_scored",
        }
        has_placeholder_uncertain = any(
            entry.get("diagnostic_status") == DiagnosticStatus.UNCERTAIN.value
            and entry.get("score_provenance") in placeholder_provenances
            for entry in syllables
        )
        has_incorrect_syllable = any(
            entry.get("diagnostic_status") == DiagnosticStatus.INCORRECT.value
            for entry in syllables
        )
        has_invalid_syllable = any(
            entry.get("diagnostic_status") == DiagnosticStatus.INVALID_AUDIO.value
            for entry in syllables
        )
        if word_decision.status is DiagnosticStatus.INVALID_AUDIO or has_invalid_syllable:
            final_word_status = DiagnosticStatus.INVALID_AUDIO
        elif has_incorrect_syllable:
            # The min-rule safety net: one syllable moving the wrong way
            # fails the word even if the whole-word shape happens to look OK.
            final_word_status = DiagnosticStatus.INCORRECT
        elif (
            word_decision.status is DiagnosticStatus.UNCERTAIN
            and word_decision.reason == "shape_direction_disagreement"
        ):
            # Shape/direction disagreement at the word level — the refactor's
            # central invariant. Never CORRECT.
            final_word_status = DiagnosticStatus.UNCERTAIN
        elif word_decision.status is DiagnosticStatus.CORRECT and not has_placeholder_uncertain:
            # Word-level shape+direction both cleared their thresholds AND
            # no syllable's UNCERTAIN comes from a placeholder that would
            # need to be re-recorded. Trust the word-level evidence.
            final_word_status = DiagnosticStatus.CORRECT
        elif syllable_rollup is DiagnosticStatus.CORRECT:
            # Every measurable syllable was clearly correct even if the
            # whole-word shape barely missed strong. Trust per-syllable.
            final_word_status = DiagnosticStatus.CORRECT
        elif syllable_rollup is not None:
            final_word_status = syllable_rollup
        else:
            final_word_status = word_decision.status
        word_diagnostic = final_word_status.value

        # When the word verdict is CORRECT via whole-word evidence but the
        # per-syllable coarse-heuristic diagnosis landed in UNCERTAIN, the
        # syllables' `passed` field must follow the word — otherwise the
        # sentence-level 80% pass-rate gate (main.build_pronunciation_mastery)
        # counts zero passing syllables and blocks a recording the word
        # verdict has already promoted. `diagnostic_status` stays honest
        # (△ still shown) — the two are allowed to disagree, but `passed`
        # is a GATE flag while `diagnostic_status` is a per-syllable
        # DIAGNOSIS. Placeholder syllables are exempt: their UNCERTAIN
        # comes from having no measurement, not from ambiguous evidence,
        # and they must not silently pass.
        if final_word_status is DiagnosticStatus.CORRECT and segment_judged:
            for entry in syllables:
                if entry.get("score_provenance") in placeholder_provenances:
                    continue
                if entry.get("passed") is not True:
                    entry["passed"] = True

        # `passed` is now derived from the canonical verdict, not a raw
        # score threshold. Only CORRECT is a pass; UNCERTAIN blocks unlock
        # (per the refactor's UNCERTAIN != CORRECT invariant).
        # `segment_judged=False` (non-Chinese token, or too little pitch to
        # judge this word) stays None — "nothing to gate on" is not a fail.
        if not segment_judged:
            word_passed = None
        else:
            word_passed = final_word_status == DiagnosticStatus.CORRECT

        # Idealized target shape for this word, scaled to its own time span
        # and pitch range so the frontend can overlay "your pitch" against
        # "target shape" directly — the visual answer to "how do I fix this?"
        reference_contour = (
            scaled_reference_contour(
                expected_tones, segment_start, segment_end,
                float(np.min(frequencies)), float(np.max(frequencies)),
                shape_override=reference_curve,
            )
            if is_chinese and (expected_tones or reference_curve)
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
                "user_curve": [round(v, 3) for v in user_curve],
                "target_curve": [round(v, 3) for v in target_curve],
                "reference_source": "real_voice" if reference_curve else "synthetic",
                "mean_pitch": round(mean_pitch, 2),
                "pitch_range": round(pitch_range, 2),
                "start_pitch": round(start_pitch, 2),
                "end_pitch": round(end_pitch, 2),
                "contour_shape": contour_shape,
                "expected_tones": expected_tones,
                "judged": segment_judged,
                "confidence": (
                    round(
                        min(
                            1.0,
                            len(scoring_points) / max(minimum_points * 2, 1),
                        ),
                        2,
                    )
                    if segment_judged
                    else 0.0
                ),
                "evidence": {
                    "pitch_points": len(scoring_points),
                    "minimum_pitch_points": minimum_points,
                },
                "tone_accuracy": round(tone_score, 1),
                "shape_accuracy": round(shape_score, 1),
                # Refactor: shape and direction surfaced as their own
                # numbers so consumers can see disagreement rather than
                # inheriting a blended score; display_score is the
                # shape-weighted composite (70/30) shown to learners in
                # progress history and is intentionally not a verdict input.
                "shape_score": round(shape_score, 1) if segment_judged else None,
                "direction_score": (
                    round(direction_score, 1) if segment_judged else None
                ),
                "display_score": word_decision.display_score,
                "verdict": word_diagnostic,
                "reason": word_decision.reason,
                "syllables": syllables,
                "passed": word_passed,
                "diagnostic_status": word_diagnostic,
                "is_content_word": is_content,
                "prominence_score": 0.0,  # filled in below after utterance mean is known
                "feedback": (
                    _word_prosody_feedback(
                        contour_shape, pitch_range, expected_tones, shape_score
                    )
                    if segment_judged or not expected_tones
                    else "Not enough voiced pitch to judge this word safely. Record it again."
                ),
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


def slice_reference_word_span(
    sentence_text: str,
    word: str,
    pitch_contour: List[Tuple[float, float]],
    search_from: int = 0,
) -> "Tuple[float, float, int] | None":
    """Approximate the time span `word` occupies within a TTS-synthesized
    reference recording of `sentence_text`, for slicing a per-word model-voice
    clip out of that one sentence recording.

    Character position within the sentence text is used as a proportional
    time proxy — the same simplification `estimate_word_prosody` uses for a
    student's own transcription — refined by snapping to the nearest real
    voicing onset. Returns (start, end, next_search_from) so repeated calls
    for a scene's word list can search forward past words already matched
    when a word appears more than once in the sentence. Returns None if the
    word doesn't appear in the sentence text from `search_from` onward.
    """
    char_index = sentence_text.find(word, search_from)
    if char_index < 0 or not pitch_contour or not word:
        return None

    total_chars = max(len(sentence_text), 1)
    start_time = float(pitch_contour[0][0])
    end_time = float(pitch_contour[-1][0])
    duration = max(end_time - start_time, 0.01)
    avg_char_duration = duration / total_chars

    proportional_start = start_time + duration * (char_index / total_chars)
    proportional_end = start_time + duration * ((char_index + len(word)) / total_chars)

    onset_times = _voicing_onset_times(pitch_contour)
    snapped_start = _snap_to_onset(proportional_start, onset_times, avg_char_duration)
    snapped_end = _snap_to_onset(proportional_end, onset_times, avg_char_duration)
    if snapped_end <= snapped_start:
        snapped_end = min(end_time, snapped_start + avg_char_duration * len(word))

    return snapped_start, snapped_end, char_index + len(word)


def reference_curve_for_span(
    pitch_contour: List[Tuple[float, float]],
    start_time: float,
    end_time: float,
) -> List[float]:
    """The normalized [0, 1], 100-point shape curve for the pitch points
    inside [start_time, end_time] of a reference recording — the same shape
    `normalize_pitch_contour` produces for a student attempt, cached here so
    it can later be sent back as a real-voice scoring override (see
    ``chinese_tones.calculate_phrase_tone_accuracy``'s ``target_curve_override``).
    """
    from chinese_tones import normalize_pitch_contour

    points = [(t, f) for t, f in pitch_contour if start_time <= t <= end_time]
    if len(points) < 2:
        return []
    return normalize_pitch_contour(points).tolist()


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


def _reference_curve_for_token(
    token: str,
    reference_word_curves: Dict[str, List[float]] | None,
) -> List[float] | None:
    """Resolve a cached model curve for the scorer's token.

    Teacher vocabulary is intentionally phrase-sized (for example ``做什麼``),
    while jieba may split the same sentence into ``做`` and ``什麼``. The old
    exact-key lookup silently dropped both sub-tokens and fell back to a
    synthetic tone contour. Split a containing reference curve by its Hanzi
    character offsets so the reference and the scorer use the same units.
    """
    if not token or not reference_word_curves:
        return None

    exact = reference_word_curves.get(token)
    if isinstance(exact, list) and exact:
        return exact

    candidates = [
        (source, curve)
        for source, curve in reference_word_curves.items()
        if isinstance(source, str)
        and token in source
        and isinstance(curve, list)
        and curve
        and len(source) > len(token)
    ]
    if not candidates:
        return None

    source, curve = min(candidates, key=lambda item: len(item[0]))
    offset = source.find(token)
    start = round(offset / len(source) * len(curve))
    end = round((offset + len(token)) / len(source) * len(curve))
    start = max(0, min(start, len(curve) - 1))
    end = max(start + 1, min(end, len(curve)))
    segment = curve[start:end]
    if len(segment) == 100:
        return segment
    # phrase_shape_curves compares fixed-length normalized arrays. Preserve
    # the sub-phrase shape while putting it back on that shared 100-point
    # contract after splitting a longer teacher phrase.
    positions = np.linspace(0.0, 1.0, len(segment))
    target_positions = np.linspace(0.0, 1.0, 100)
    return np.interp(target_positions, positions, np.asarray(segment, dtype=float)).tolist()


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


# One concrete "do this with your voice" instruction per tone — the anchors
# (question intonation, a firm command, humming a note) are cross-language
# vocal gestures an A1-A2 learner can imitate without phonetics vocabulary.
_TONE_EXAGGERATION_TIPS = {
    1: "hold one steady, level note from start to end, like humming a single musical note",
    2: "climb clearly from mid to high, like asking “huh?”",
    3: "drop to your lowest pitch before the small rise — the low point is the goal",
    4: "fall fast and firm from high to low, like a short command",
}


def _tone_mismatch_diagnosis(expected_tone: int, contour_shape: str) -> str:
    """What actually went wrong, in terms of what the student's own pitch
    did versus what the target tone does — so the fix is a specific vocal
    action, not a restatement of the score."""
    if expected_tone == 1:
        if contour_shape in {"rising", "falling", "dip", "variable"}:
            return (
                "Your pitch moved around — Tone 1 holds one steady level "
                "note from start to end, like humming a single musical note."
            )
    elif expected_tone == 2:
        if contour_shape == "falling":
            return (
                "Your pitch fell — Tone 2 rises: start mid and lift to "
                "high, like asking “huh?”"
            )
        if contour_shape == "level":
            return (
                "Too flat — Tone 2 must climb clearly from mid to high, "
                "like the end of a question."
            )
        return (
            "Tone 2 is one smooth rise, mid to high — no dip on the way, "
            "just up, like asking a question."
        )
    elif expected_tone == 3:
        if contour_shape == "rising":
            return (
                "You rose right away — Tone 3 dips first: start mid, drop "
                "low, then relax back up."
            )
        if contour_shape == "falling":
            return (
                "You fell but didn't come back — Tone 3 drops low, then "
                "bounces lightly up at the end."
            )
        if contour_shape == "level":
            return (
                "Too flat — Tone 3 needs a clear drop to your lowest "
                "pitch before the small rise."
            )
        return (
            "Make the dip deeper: mid → low → small rise. The low "
            "point is the goal."
        )
    elif expected_tone == 4:
        if contour_shape == "rising":
            return (
                "Your pitch rose — Tone 4 falls: start high and drop fast "
                "and firm, like a short command."
            )
        if contour_shape == "level":
            return (
                "Too flat — Tone 4 needs a sharp fall from high to low."
            )
        return (
            "One clean fall, high to low, no bounce — short and firm "
            "like a command."
        )
    return ""


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
    score that can rate a wrong-shaped-but-right-direction attempt as "good".

    The three tiers keep their stable lead-in strings ("Good match" /
    "Recognizable" / "Expected ... doesn't match yet") — the frontend's
    prosodyImprovementTip keys off them — but the two problem tiers now end
    with a concrete vocal action derived from what the student's pitch
    actually did, instead of only restating that it was wrong.
    """
    if expected_tones:
        tone_label = "+".join(_TONE_NAMES.get(t, str(t)) for t in expected_tones)
        # First non-neutral tone anchors the diagnosis: it's the syllable
        # with a real target shape, and for 1-2 syllable A1-A2 words it is
        # almost always the word's tonal center.
        primary_tone = next((t for t in expected_tones if t in (1, 2, 3, 4)), None)

        if shape_score >= 68:
            return f"Good match for {tone_label}."
        if shape_score >= 48:
            tip = _TONE_EXAGGERATION_TIPS.get(primary_tone or 0, "")
            suffix = f" Exaggerate it: {tip}." if tip else ""
            return f"Recognizable {tone_label}, but contrast could be sharper.{suffix}"
        diagnosis = (
            _tone_mismatch_diagnosis(primary_tone, contour_shape)
            if primary_tone
            else ""
        )
        suffix = f" {diagnosis}" if diagnosis else ""
        return f"Expected {tone_label} — pitch shape doesn't match yet.{suffix}"

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
