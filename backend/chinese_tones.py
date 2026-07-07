from typing import Dict, List, Tuple

import numpy as np
from pypinyin import Style, pinyin
import taiwan_pinyin; taiwan_pinyin.apply()
from scipy.interpolate import interp1d
from scipy.spatial.distance import euclidean


TONE_REFERENCES = {
    1: {
        "name": "High Level",
        "character": "媽",
        "pinyin": "ma1",
        "description": "High and flat",
        "pitch_pattern": [0.8, 0.8, 0.8, 0.8, 0.8],
        "frequency_range": (200, 300),
        "expected_mean": 250,
    },
    2: {
        "name": "Rising",
        "character": "麻",
        "pinyin": "ma2",
        "description": "Rising from mid to high",
        "pitch_pattern": [0.5, 0.6, 0.7, 0.8, 0.85],
        "frequency_range": (200, 300),
        "expected_mean": 240,
    },
    3: {
        "name": "Falling-Rising",
        "character": "馬",
        "pinyin": "ma3",
        "description": "Falls then rises",
        "pitch_pattern": [0.7, 0.5, 0.3, 0.5, 0.7],
        "frequency_range": (100, 250),
        "expected_mean": 200,
    },
    4: {
        "name": "Falling",
        "character": "罵",
        "pinyin": "ma4",
        "description": "High to low falling sharply",
        "pitch_pattern": [0.9, 0.75, 0.6, 0.4, 0.2],
        "frequency_range": (100, 300),
        "expected_mean": 200,
    },
}


def get_reference_tone_pattern(tone_number: int, num_points: int = 100) -> Dict:
    if tone_number not in TONE_REFERENCES:
        return None

    ref = TONE_REFERENCES[tone_number]
    x = np.linspace(0, 1, len(ref["pitch_pattern"]))
    x_new = np.linspace(0, 1, num_points)
    interpolator = interp1d(x, ref["pitch_pattern"], kind="cubic", fill_value="extrapolate")
    interpolated = np.clip(interpolator(x_new), 0, 1)

    return {
        "tone": tone_number,
        "name": ref["name"],
        "character": ref["character"],
        "pinyin": ref["pinyin"],
        "description": ref["description"],
        "pitch_pattern": interpolated.tolist(),
        "frequency_range": ref["frequency_range"],
        "expected_mean": ref["expected_mean"],
    }


def normalize_pitch_contour(
    pitch_contour: List[Tuple[float, float]],
    outlier_z: float = 2.5,
    min_std_hz: float = 6.0,
) -> np.ndarray:
    """Normalize a pitch contour's shape to [0, 1] for tone-pattern comparison.

    Uses speaker-relative z-score normalization rather than raw min-max: a
    single stray frame (e.g. an uncorrected octave error, or a brief voicing
    glitch) can otherwise stretch the whole 0-1 range and flatten every other
    point's relative shape. Z-scores are clipped to ``outlier_z`` standard
    deviations before rescaling so one extreme point can't dominate the range.
    """
    if not pitch_contour or len(pitch_contour) < 2:
        return np.array([])

    times = np.array([point[0] for point in pitch_contour])
    frequencies = np.array([point[1] for point in pitch_contour])

    duration = times[-1] - times[0]
    if duration <= 0:
        return np.array([])

    times_norm = (times - times[0]) / duration

    # Median/MAD rather than mean/std: a single octave-error spike inflates
    # the standard deviation (since it's part of the same calculation being
    # used to clip it), which softens every other point's z-score right
    # along with the outlier's. The median-based scale is robust to a
    # minority of extreme points by construction.
    median_freq = float(np.median(frequencies))
    mad = float(np.median(np.abs(frequencies - median_freq)))
    robust_std = mad * 1.4826  # MAD-to-std scaling factor for normal data
    if robust_std < min_std_hz:
        # Genuinely flat pitch (e.g. Tone 1): dividing by a near-zero scale
        # would blow tiny measurement jitter up into a full-range shape, so
        # fall back to a flat midpoint instead of z-scoring it.
        frequencies_norm = np.ones_like(frequencies) * 0.5
    else:
        z_scores = np.clip((frequencies - median_freq) / robust_std, -outlier_z, outlier_z)
        frequencies_norm = (z_scores + outlier_z) / (2 * outlier_z)

    x_new = np.linspace(0, 1, 100)
    interpolator = interp1d(times_norm, frequencies_norm, kind="linear", fill_value="extrapolate")
    return np.clip(interpolator(x_new), 0, 1)


FLAT_REFERENCE_VARIANCE_THRESHOLD = 0.015


def _shape_match_score(user_pitch: np.ndarray, ref_pitch: np.ndarray) -> float:
    """Correlation + distance shape-similarity score between two equal-length
    curves already on ``normalize_pitch_contour``'s [0, 1] scale, as 0-100.

    Shared by ``calculate_tone_accuracy`` (single reference tone) and
    ``calculate_phrase_tone_accuracy`` (concatenated phrase reference) so a
    fix to the underlying math only has to happen in one place.
    """
    if float(np.var(ref_pitch)) < 1e-6:
        # A flat reference (Tone 1, or an all-neutral-tone phrase) has zero
        # variance, so Pearson correlation against it is mathematically
        # undefined -- corrcoef divides by a zero standard deviation. Silently
        # defaulting that NaN to 0.0 (a neutral 0.5 after rescaling) handed
        # *every* contour the same baseline correlation credit regardless of
        # whether it was actually flat or a full swing in the wrong
        # direction. Score flatness directly instead: how little the user's
        # own normalized contour varies.
        user_variance = float(np.var(user_pitch))
        flatness = max(0.0, 1.0 - user_variance / FLAT_REFERENCE_VARIANCE_THRESHOLD) * 100.0
        return float(max(0.0, min(100.0, flatness)))

    correlation = np.corrcoef(user_pitch, ref_pitch)[0, 1]
    if np.isnan(correlation):
        correlation = 0.0

    # Mean-center both curves before measuring distance, so a flat user
    # contour pitched a bit above or below where a reference pattern happens
    # to sit doesn't get penalized for *level* rather than *shape* — that
    # level difference is already irrelevant after normalize_pitch_contour.
    distance = euclidean(user_pitch - np.mean(user_pitch), ref_pitch - np.mean(ref_pitch))
    # Euclidean distance across `n` dimensions each bounded to [-0.5, 0.5]
    # scales with sqrt(n), not n: dividing by n (the old code) squashed
    # distance_score into a near-constant ~0.95-1.0 band regardless of match
    # quality, making the nominal 35% distance weight almost inert. Dividing
    # by sqrt(n) restores its actual [0, 1] range so it discriminates.
    distance_score = max(0.0, 1.0 - distance / np.sqrt(len(user_pitch)))
    correlation_score = (correlation + 1.0) / 2.0
    accuracy = (correlation_score * 0.65 + distance_score * 0.35) * 100.0
    return float(max(0.0, min(100.0, accuracy)))


def calculate_tone_accuracy(
    pitch_contour: List[Tuple[float, float]], tone_number: int
) -> float:
    user_pitch = normalize_pitch_contour(pitch_contour)
    if len(user_pitch) == 0:
        return 0.0

    ref = get_reference_tone_pattern(tone_number, num_points=len(user_pitch))
    ref_pitch = np.array(ref["pitch_pattern"])
    return _shape_match_score(user_pitch, ref_pitch)


def detect_tone(pitch_contour: List[Tuple[float, float]]) -> Dict:
    if not pitch_contour or len(pitch_contour) < 2:
        return {
            "detected_tone": 0,
            "confidence": 0.0,
            "scores": {1: 0, 2: 0, 3: 0, 4: 0},
            "feedback": "Unable to detect tone. Audio too short or unclear.",
        }

    scores = {
        tone_num: calculate_tone_accuracy(pitch_contour, tone_num)
        for tone_num in [1, 2, 3, 4]
    }
    detected_tone = max(scores, key=scores.get)
    confidence = scores[detected_tone] / 100.0
    ref = TONE_REFERENCES[detected_tone]

    return {
        "detected_tone": detected_tone,
        "confidence": float(confidence),
        "scores": {key: float(value) for key, value in scores.items()},
        "feedback": f"Detected: {ref['name']} tone ({ref['character']}, {ref['pinyin']})",
        "reference": ref,
    }


def word_tones(word: str) -> List[int]:
    """Look up the expected tone (1-4, 5 = neutral) for each character in a word.

    Uses pypinyin's dictionary, so this is the *expected* tone from the
    written word — independent of what the student actually said.
    """
    tones: List[int] = []
    for syllable in pinyin(word, style=Style.TONE3, neutral_tone_with_five=True):
        digits = "".join(c for c in syllable[0] if c.isdigit())
        tones.append(int(digits) if digits else 5)
    return tones


def apply_tone_sandhi(tones: List[int]) -> List[int]:
    """Apply the third-tone sandhi rule: tone3 followed by tone3 -> tone2 + tone3.

    This is the one sandhi pattern common enough in short student phrases to be
    worth correcting for; other sandhi (e.g. 一/不 tone changes) is out of scope.
    """
    adjusted = list(tones)
    for i in range(len(adjusted) - 1):
        if adjusted[i] == 3 and adjusted[i + 1] == 3:
            adjusted[i] = 2
    return adjusted


def build_phrase_reference_pattern(tones: List[int], num_points: int = 100) -> np.ndarray:
    """Concatenate single-syllable reference contours into one phrase-length curve.

    Each syllable gets an equal time slice (same simplification used for the
    audio side in ``estimate_word_prosody``), so the two contours line up
    syllable-for-syllable when compared.
    """
    if not tones:
        return np.full(num_points, 0.5)

    per_syllable = max(1, num_points // len(tones))
    pieces = []
    for tone in tones:
        ref = TONE_REFERENCES.get(tone, TONE_REFERENCES[1])
        if tone == 5:
            # Neutral tone: short, low, and flat — not one of the four canonical shapes.
            pattern = [0.35, 0.35]
        else:
            pattern = ref["pitch_pattern"]
        x = np.linspace(0, 1, len(pattern))
        x_new = np.linspace(0, 1, per_syllable)
        interpolator = interp1d(x, pattern, kind="linear", fill_value="extrapolate")
        pieces.append(np.clip(interpolator(x_new), 0, 1))

    combined = np.concatenate(pieces)
    if len(combined) != num_points:
        x = np.linspace(0, 1, len(combined))
        x_new = np.linspace(0, 1, num_points)
        interpolator = interp1d(x, combined, kind="linear", fill_value="extrapolate")
        combined = np.clip(interpolator(x_new), 0, 1)
    return combined


def scaled_reference_contour(
    tones: List[int],
    start_time: float,
    end_time: float,
    pitch_min: float,
    pitch_max: float,
    num_points: int = 20,
) -> List[Tuple[float, float]]:
    """Build the idealized reference pitch curve for a word's expected tones,
    scaled to that word's own time span and pitch range so it can be plotted
    directly alongside the student's measured contour for visual comparison.

    Scaled to the word's own min/max (not TONE_REFERENCES' absolute Hz bands)
    for the same reason ``normalize_pitch_contour`` is speaker-relative: the
    reference is a *shape* target, not an absolute-pitch target, so the
    overlay stays meaningful across speakers, genders, and mic gain.
    """
    if not tones or end_time <= start_time:
        return []

    shape = build_phrase_reference_pattern(tones, num_points=num_points)

    # TONE_REFERENCES' raw pattern values only occupy a narrow sub-band (e.g.
    # tone 2 is [0.5, 0.85], not [0, 1]) because the scoring math compares
    # shapes by correlation, which is scale/offset invariant — it doesn't
    # care where in [0, 1] the pattern sits. But drawing that sub-band as-is
    # onto the full pitch box makes the target curve look squashed into a
    # corner even when the actual recording correlates with it well, so the
    # overlay reads as "doesn't match" for a genuinely good attempt. Re-
    # normalizing to span exactly [0, 1] first makes the drawn shape occupy
    # the same vertical range as the actual curve, matching what correlation
    # actually rewards.
    shape_min = float(np.min(shape))
    shape_max = float(np.max(shape))
    shape_span = shape_max - shape_min
    if shape_span < 0.05:
        # Genuinely flat target (tone 1): keep it a flat midline rather than
        # blow negligible interpolation jitter up into the full range.
        shape_norm = np.full_like(shape, 0.5)
    else:
        shape_norm = (shape - shape_min) / shape_span

    span = max(pitch_max - pitch_min, 1.0)
    times = np.linspace(start_time, end_time, num_points)
    return [(float(t), float(pitch_min + s * span)) for t, s in zip(times, shape_norm)]


def calculate_directional_tone_accuracy(
    pitch_contour: List[Tuple[float, float]], tones: List[int]
) -> float:
    """Directional / ordinal tone scoring tuned for connected speech.

    Instead of comparing against an idealized isolated-syllable reference curve,
    this checks only whether pitch *moves in the right direction* within each
    syllable window.  This is far more robust to the declination, coarticulation,
    and speaking-rate effects that distort tone shapes in natural running speech:

        T1 (flat)    — variance within the syllable window is low
        T2 (rising)  — end-region pitch > start-region pitch
        T4 (falling) — start-region pitch > end-region pitch
        T3 (dip)     — midpoint is lower than the average of start and end
        T5 (neutral) — generously rewarded; shape is context-dependent

    Regional means (first/last quarter of each syllable window) are used instead
    of single-frame endpoints so that edge noise does not dominate the score.

    Returns a score in [0, 100].
    """
    user_pitch = normalize_pitch_contour(pitch_contour)
    if len(user_pitch) == 0 or not tones:
        return 0.0

    tones_s = apply_tone_sandhi(tones)
    n = len(tones_s)
    syl_len = max(1, len(user_pitch) // n)

    scores: List[float] = []
    for i, tone in enumerate(tones_s):
        start_idx = i * syl_len
        end_idx = start_idx + syl_len if i < n - 1 else len(user_pitch)
        seg = user_pitch[start_idx:end_idx]

        if len(seg) < 4:
            scores.append(65.0)  # too short to judge; give benefit of the doubt
            continue

        q = max(1, len(seg) // 4)  # quarter-length for regional means

        s_mean = float(np.mean(seg[:q]))         # start-region mean
        e_mean = float(np.mean(seg[-q:]))        # end-region mean
        mid_seg = seg[q: len(seg) - q]           # middle 50 %
        mid_min = float(np.min(mid_seg)) if len(mid_seg) else float(np.min(seg))
        variance = float(np.var(seg))

        if tone == 1:
            # Flat: low intra-syllable variance.
            # variance=0 → 100, variance≥0.12 → 0
            score = max(0.0, 1.0 - variance / 0.12) * 100.0

        elif tone == 2:
            # Rising: end-region above start-region.
            # rise=+0.5 → 100, rise=0 → 50, rise=-0.5 → 0
            rise = e_mean - s_mean
            score = max(0.0, min(1.0, (rise + 0.5) / 1.0)) * 100.0

        elif tone == 4:
            # Falling: start-region above end-region.
            fall = s_mean - e_mean
            score = max(0.0, min(1.0, (fall + 0.5) / 1.0)) * 100.0

        elif tone == 3:
            # Dip: midpoint below the average of start and end regions.
            # dip_depth=+0.4 (deep V) → 100, dip_depth=0 (flat) → 45, negative → low
            avg_endpoints = (s_mean + e_mean) / 2.0
            dip_depth = avg_endpoints - mid_min
            score = max(0.0, min(1.0, (dip_depth + 0.25) / 0.55)) * 100.0

        else:
            # Neutral tone 5: short and light; no fixed pitch shape to grade.
            score = 75.0

        scores.append(score)

    return float(np.mean(scores)) if scores else 0.0


def calculate_phrase_tone_accuracy(
    pitch_contour: List[Tuple[float, float]], tones: List[int]
) -> float:
    """Score a pitch contour against the *expected* tone sequence for a word/phrase.

    Blends two complementary components:

    • Shape matching (30 %) — correlation + distance against the idealized
      reference contour; rewards students who nail the full tone shape in
      careful, isolated-word speech.

    • Directional scoring (70 %) — checks only pitch *direction* per syllable
      (rising / falling / flat / dip).  Robust to the declination, coarticulation
      and speaking-rate effects that distort tone shapes in natural connected
      speech, so a learner speaking fluently is not unfairly penalized.
    """
    if not pitch_contour or not tones:
        return 0.0

    user_pitch = normalize_pitch_contour(pitch_contour)
    if len(user_pitch) == 0:
        return 0.0

    # ── Shape-matching component (original algorithm) ──────────────────────
    ref_pitch = build_phrase_reference_pattern(apply_tone_sandhi(tones), num_points=len(user_pitch))
    shape_score = _shape_match_score(user_pitch, ref_pitch)

    # ── Directional component (connected-speech robust) ─────────────────────
    directional_score = calculate_directional_tone_accuracy(pitch_contour, tones)

    return float(max(0.0, min(100.0, shape_score * 0.30 + directional_score * 0.70)))


def get_tone_feedback(
    detected_tone: int, accuracy: float, pitch_contour: List[Tuple[float, float]]
) -> str:
    if not pitch_contour or detected_tone not in TONE_REFERENCES:
        return "No clear tone detected yet. Try recording a slightly longer phrase."

    ref = TONE_REFERENCES[detected_tone]
    feedback_parts = []

    if accuracy > 85:
        feedback_parts.append(f"Excellent {ref['name']} tone.")
    elif accuracy > 70:
        feedback_parts.append(f"Good {ref['name']} tone.")
    elif accuracy > 55:
        feedback_parts.append(f"The {ref['name']} tone is recognizable.")
    else:
        feedback_parts.append(f"The {ref['name']} tone needs more contrast.")

    frequencies = np.array([point[1] for point in pitch_contour])
    mean_freq = np.mean(frequencies)
    freq_range = TONE_REFERENCES[detected_tone]["frequency_range"]

    if freq_range[0] <= mean_freq <= freq_range[1]:
        feedback_parts.append(f"Pitch range is on target at about {mean_freq:.0f} Hz.")
    elif mean_freq < freq_range[0]:
        feedback_parts.append(f"Pitch is low; aim closer to {freq_range[0]}-{freq_range[1]} Hz.")
    else:
        feedback_parts.append(f"Pitch is high; aim closer to {freq_range[0]}-{freq_range[1]} Hz.")

    if detected_tone == 1:
        if np.std(np.diff(frequencies)) < 20:
            feedback_parts.append("Keep that steady, level pitch.")
        else:
            feedback_parts.append("Tone 1 should stay flatter.")
    elif detected_tone == 2:
        feedback_parts.append(
            "Good upward slope." if frequencies[-1] > frequencies[0]
            else "Tone 2 should rise from lower to higher pitch."
        )
    elif detected_tone == 3 and len(frequencies) >= 3:
        mid_idx = len(frequencies) // 2
        feedback_parts.append(
            "Good dip in the middle."
            if frequencies[mid_idx] < frequencies[0] and frequencies[mid_idx] < frequencies[-1]
            else "Tone 3 needs a clearer dip in the middle."
        )
    elif detected_tone == 4:
        feedback_parts.append(
            "Good falling slope." if frequencies[-1] < frequencies[0]
            else "Tone 4 should fall from high to low."
        )

    return " ".join(feedback_parts)


def _tone_label(tone: int) -> str:
    if tone == 5:
        return "neutral tone"
    ref = TONE_REFERENCES.get(tone)
    return ref["name"] if ref else f"tone {tone}"


def generate_phrase_tone_feedback(word_prosody: List[Dict], tone_accuracy: float) -> str:
    """Build tone feedback grounded in the same per-word scores that produced
    ``tone_accuracy``, so the text and the number never contradict each other —
    unlike describing one canonical tone shape against the whole recording.
    """
    scored = [w for w in word_prosody if w.get("expected_tones")]
    if not scored:
        return "No clear tone detected yet. Try recording a slightly longer phrase."

    # Connected speech (multiple words) naturally compresses tone contours:
    # adjacent T4+T4 flatten, T2 rises less steeply before a following fall,
    # and declination lowers everything toward the end of a phrase. A fluent
    # sentence therefore tops out ~10 points below an isolated syllable, so we
    # relax the grading bands once there are several words to score. Single
    # words keep the stricter isolated-syllable bands.
    if len(scored) >= 3:
        excellent, good, recognizable = 65.0, 50.0, 38.0
    elif len(scored) == 2:
        excellent, good, recognizable = 70.0, 54.0, 41.0
    else:
        excellent, good, recognizable = 75.0, 58.0, 44.0

    if tone_accuracy > excellent:
        lead = "Excellent tone accuracy overall."
    elif tone_accuracy > good:
        lead = "Good tone accuracy overall."
    elif tone_accuracy > recognizable:
        lead = "Tones are recognizable but inconsistent."
    else:
        lead = "Tones need more contrast overall."

    parts = [lead]
    weakest = min(scored, key=lambda w: w["tone_accuracy"])
    strongest = max(scored, key=lambda w: w["tone_accuracy"])

    if weakest["tone_accuracy"] < 58:
        tone_label = "+".join(_tone_label(t) for t in weakest["expected_tones"])
        parts.append(f'"{weakest["token"]}" ({tone_label}) needs the clearest work.')
    if strongest is not weakest and strongest["tone_accuracy"] >= 68:
        parts.append(f'"{strongest["token"]}" sounded solid.')

    return " ".join(parts)


def generate_comprehensive_feedback(
    detected_tone: int,
    tone_accuracy: float,
    speech_rate: float,
    fluency: float,
    pitch_contour: List[Tuple[float, float]],
    word_prosody: List[Dict] | None = None,
) -> str:
    tone_feedback = (
        generate_phrase_tone_feedback(word_prosody, tone_accuracy)
        if word_prosody
        else get_tone_feedback(detected_tone, tone_accuracy, pitch_contour)
    )
    feedback_parts = [tone_feedback]

    if speech_rate > 0:
        if 3.5 <= speech_rate <= 5.5:
            feedback_parts.append(f"Speech rate is comfortable at {speech_rate:.1f} syllables/sec.")
        elif speech_rate < 3.5:
            feedback_parts.append(f"Try a little faster; current rate is {speech_rate:.1f} syllables/sec.")
        else:
            feedback_parts.append(f"Slow down slightly; current rate is {speech_rate:.1f} syllables/sec.")

    if fluency > 80:
        feedback_parts.append("Fluency is smooth.")
    elif fluency > 60:
        feedback_parts.append("Work on smoother pitch transitions.")
    else:
        feedback_parts.append("Try one shorter phrase and keep the tone movement clear.")

    return " ".join(feedback_parts)
