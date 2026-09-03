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
    target_phrases: List[str] | None = None,
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

    ``target_phrases``, when given, is passed straight through to
    ``estimate_word_prosody`` for the phrase-context rescue — see
    ``_apply_phrase_rescue``.

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
            target_phrases=target_phrases,
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
        target_phrases=target_phrases,
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
