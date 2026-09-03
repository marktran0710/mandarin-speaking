from typing import Dict, List, Tuple

import numpy as np
from scipy.interpolate import interp1d
from scipy.ndimage import median_filter
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
    from pinyin_service import canonical_pinyin_tone3

    tones: List[int] = []
    for syllable in canonical_pinyin_tone3(word).split():
        digits = "".join(c for c in syllable if c.isdigit())
        tones.append(int(digits) if digits else 5)
    return tones


_TONE_MARK_TONES = {
    "ā": 1, "á": 2, "ǎ": 3, "à": 4,
    "ē": 1, "é": 2, "ě": 3, "è": 4,
    "ī": 1, "í": 2, "ǐ": 3, "ì": 4,
    "ō": 1, "ó": 2, "ǒ": 3, "ò": 4,
    "ū": 1, "ú": 2, "ǔ": 3, "ù": 4,
    "ǖ": 1, "ǘ": 2, "ǚ": 3, "ǜ": 4,
}


def syllable_parts(word: str) -> List[Tuple[str, str]]:
    """Split each character of ``word`` into its (initial, final) pinyin parts.

    e.g. "在家" -> [("z", "ai"), ("j", "ia")]. The initial is "" for a
    zero-initial syllable (啊 -> ("", "a")). Finals come back toneless, and ü
    is spelled "v" the way pypinyin writes it.

    Used by the vowel readout to know which vowel the character is *supposed*
    to carry, and to recognise the syllabic -i of zhi/chi/shi/ri/zi/ci/si —
    which is written "i" but is not the vowel /i/, so it must never be judged
    against one.
    """
    from pinyin_service import canonical_syllable_parts

    return canonical_syllable_parts(word)


def parse_pinyin_tones(pinyin_text: str) -> List[int]:
    """Parse one tone (1-4, 5 = neutral) per space-separated syllable.

    Both tone-marked pinyin (``jiě jie``) and numeric pinyin
    (``jie3 jie5``) are accepted. Supporting both formats matters because the
    frontend displays tone marks while a number of upload/API clients send
    tone-number pinyin.

    This exists so a word's *displayed* pinyin — whether pypinyin's own guess
    or a teacher's manually corrected ``vocabularyPinyin`` — can be used
    directly as the scoring/target-shape reference, instead of a second,
    independent pypinyin lookup on the character that could silently
    disagree with what the student is actually looking at.

    A syllable with no tone mark or trailing tone digit is treated as neutral
    (5). Returns [] for blank input.
    """
    syllables = pinyin_text.strip().split()
    tones: List[int] = []
    for syllable in syllables:
        tone = 5
        for ch in syllable:
            if ch in _TONE_MARK_TONES:
                tone = _TONE_MARK_TONES[ch]
                break
        else:
            # Accept canonical tone-number pinyin such as ``ni3`` and ``me5``.
            # Only a final digit is meaningful; arbitrary digits elsewhere in
            # an input token must not change the target tone.
            if syllable and syllable[-1] in "12345":
                tone = int(syllable[-1])
        tones.append(tone)
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
    shape_override: List[float] | None = None,
) -> List[Tuple[float, float]]:
    """Build the reference pitch curve for a word's expected tones, scaled to
    that word's own time span and pitch range so it can be plotted directly
    alongside the student's measured contour for visual comparison.

    Scaled to the word's own min/max (not TONE_REFERENCES' absolute Hz bands)
    for the same reason ``normalize_pitch_contour`` is speaker-relative: the
    reference is a *shape* target, not an absolute-pitch target, so the
    overlay stays meaningful across speakers, genders, and mic gain.

    ``shape_override``, when given, is a real model-voice shape curve (see
    ``praat_analyzer.reference_curve_for_span``) used in place of the
    synthetic idealized tone-shape pattern — the same override
    ``phrase_shape_curves`` accepts, so the chart never disagrees with what
    was actually scored.
    """
    if (not tones and not shape_override) or end_time <= start_time:
        return []

    if shape_override:
        x = np.linspace(0, 1, len(shape_override))
        x_new = np.linspace(0, 1, num_points)
        interpolator = interp1d(x, shape_override, kind="linear", fill_value="extrapolate")
        shape = np.clip(interpolator(x_new), 0, 1)
    else:
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


def _smooth_for_directional_scoring(pitch: np.ndarray, kernel_size: int = 5) -> np.ndarray:
    """Median-filter the normalized contour before computing the per-syllable
    start/end/mid regional means directional scoring relies on.

    ``_correct_octave_jumps`` (praat_analyzer.py) already fixes full ~2x/0.5x
    pitch-tracker errors, but a smaller in-octave wobble near a syllable
    boundary (a brief voicing glitch, not a tracking error large enough to
    trigger that correction) still lands untouched in a regional mean —
    and since directional scoring only ever averages a quarter-window, one
    or two noisy frames there can swing a syllable's score by double digits
    even when the surrounding contour matches the target shape well.
    """
    if len(pitch) < kernel_size:
        return pitch
    # mode="nearest" (edge-value replication) rather than scipy.signal.medfilt's
    # implicit zero-padding: on a [0, 1]-scaled contour, zero-padding the last
    # few frames pulls the median toward 0 right at the array boundary — which
    # is exactly where a tone-3 syllable's recovery rise (the signal this
    # function most needs to preserve) tends to sit.
    return median_filter(pitch, size=kernel_size, mode="nearest")


def directional_tone_scores(
    pitch_contour: List[Tuple[float, float]],
    tones: List[int],
    syllable_windows: List[Tuple[int, int]] | None = None,
) -> List[float]:
    """Per-syllable directional tone scores — the legacy scoring entry point.

    Behaviour is unchanged and must stay unchanged: this is the score the
    progression gate runs on (see praat_analyzer.SYLLABLE_PASS_THRESHOLD).
    Callers that also need to know *how* each score was produced should use
    ``directional_tone_scores_with_provenance`` instead; this wrapper exists
    so the legacy signature and output stay byte-identical.
    """
    return directional_tone_scores_with_provenance(
        pitch_contour, tones, syllable_windows
    )[0]


def directional_tone_scores_with_provenance(
    pitch_contour: List[Tuple[float, float]],
    tones: List[int],
    syllable_windows: List[Tuple[int, int]] | None = None,
) -> Tuple[List[float], List[str]]:
    """Scores plus, for each one, whether it was measured or filled in.

    Two of the values this function can return are not measurements:

    * ``constant_short_segment`` — the segment held too few pitch frames to
      judge, so a flat 65 is returned "to give benefit of the doubt".
    * ``neutral_not_measured``   — neutral tone has no fixed contour target
      at all, so a flat 75 is returned. Nothing about the learner was
      measured; the name says so rather than implying a weak measurement.

    Both constants sit above the legacy pass bar of 58, which means a syllable
    nobody could measure currently reads as a pass. That behaviour is left
    alone here because progression depends on it, but the provenance label
    lets the diagnostic layer refuse to treat either constant as evidence.
    See tone_decision.decide_tone.

    Returns ``(scores, provenance)``, both the same length as ``tones``.

    This is ``calculate_directional_tone_accuracy``'s scoring loop exposed
    before the final mean, so callers that need to know *which* syllable
    failed (e.g. the per-word pass gate in word prosody) can read each
    syllable window's own score instead of a whole-word average that lets a
    good second syllable hide a wrong-direction first one.

    ``syllable_windows`` gives explicit (start, end) index ranges into
    ``pitch_contour`` for each tone. Without it the contour is split into
    equal-length pieces, which assumes every syllable occupies the same amount
    of time — real Mandarin syllable durations vary by 2-3x, so that lands the
    tone template on the wrong stretch of audio. Callers that have real
    boundaries (see ``tone_scoring.alignment``) should pass them; the equal
    split remains only as the fallback for callers that do not.

    Returns ([], []) when the contour or tone list can't be scored.
    """
    user_pitch = normalize_pitch_contour(pitch_contour)
    if len(user_pitch) == 0 or not tones:
        return [], []

    user_pitch = _smooth_for_directional_scoring(user_pitch)

    tones_s = apply_tone_sandhi(tones)
    n = len(tones_s)
    syl_len = max(1, len(user_pitch) // n)
    windows = syllable_windows if syllable_windows and len(syllable_windows) == n else None

    scores: List[float] = []
    provenance: List[str] = []
    for i, tone in enumerate(tones_s):
        seg = user_pitch[slice(*_window_for(i, n, syl_len, len(user_pitch), windows))]
        score, source = _score_segment(seg, tone)
        scores.append(score)
        provenance.append(source)

    return scores, provenance
