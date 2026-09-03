

def reference_syllable_scores(
    pitch_contour: List[Tuple[float, float]],
    tones: List[int],
    reference_curve: List[float] | None,
    syllable_windows: List[Tuple[int, int]] | None = None,
) -> Tuple[List[float], List[str]]:
    """Score each syllable against a real reference contour.

    ``reference_curve`` is a normalized curve for the whole word/phrase. The
    old per-syllable scorer compared each window only with the canonical tone
    template, even when the word-level shape scorer had a teacher/TTS curve.
    That made one recording receive a high real-voice shape score and a low
    synthetic syllable score at the same time.

    The student contour is normalized to the same fixed-length contract as
    the reference, then both curves are sliced using the actual syllable
    windows. Tone 5 remains explicitly unmeasured because neutral tone has no
    fixed contour target. A too-short window keeps the existing benefit-of-
    the-doubt value, but is labelled as non-measurement by provenance.
    """
    if not pitch_contour or not tones or not reference_curve:
        return [], []

    user_pitch = normalize_pitch_contour(pitch_contour)
    if len(user_pitch) == 0:
        return [], []

    reference = np.asarray(reference_curve, dtype=float)
    if reference.size < 2 or not np.all(np.isfinite(reference)):
        return [], []

    # Cached curves normally already contain 100 points, but accepting any
    # finite length keeps old stories and hand-authored fixtures compatible.
    reference_positions = np.linspace(0.0, 1.0, reference.size)
    fixed_positions = np.linspace(0.0, 1.0, len(user_pitch))
    reference = np.interp(fixed_positions, reference_positions, reference)

    n = len(tones)
    raw_total = len(pitch_contour)
    raw_syllable_length = max(1, raw_total // n)
    windows = (
        syllable_windows
        if syllable_windows and len(syllable_windows) == n
        else None
    )

    scores: List[float] = []
    provenance: List[str] = []
    for index, tone in enumerate(apply_tone_sandhi(tones)):
        if tone == 5:
            scores.append(75.0)
            provenance.append("neutral_not_measured")
            continue

        raw_start, raw_end = _window_for(
            index, n, raw_syllable_length, raw_total, windows
        )
        normalized_start = int(round(raw_start / max(raw_total, 1) * len(user_pitch)))
        normalized_end = int(round(raw_end / max(raw_total, 1) * len(user_pitch)))
        normalized_start = max(0, min(normalized_start, len(user_pitch) - 1))
        normalized_end = max(normalized_start + 1, min(normalized_end, len(user_pitch)))
        user_segment = user_pitch[normalized_start:normalized_end]
        reference_segment = reference[normalized_start:normalized_end]

        if len(user_segment) < 4 or len(reference_segment) < 4:
            scores.append(65.0)
            provenance.append("constant_short_segment")
            continue

        # Compare at a small fixed resolution so syllables with different
        # durations contribute equally while retaining the reference shape.
        segment_positions = np.linspace(0.0, 1.0, len(user_segment))
        compare_positions = np.linspace(0.0, 1.0, 32)
        user_resampled = np.interp(compare_positions, segment_positions, user_segment)
        reference_resampled = np.interp(
            compare_positions,
            np.linspace(0.0, 1.0, len(reference_segment)),
            reference_segment,
        )
        scores.append(
            float(_shape_match_score(user_resampled, reference_resampled))
        )
        provenance.append("reference_shape")

    return scores, provenance


def contextual_tone_scores(
    pitch_contour: List[Tuple[float, float]],
    accepted_tones: List[Tuple[int, ...]],
    syllable_windows: List[Tuple[int, int]] | None = None,
) -> List[Tuple[float, int, str]]:
    """Score each syllable against every tone it is *allowed* to surface as.

    ``accepted_tones`` gives one tuple of candidate tones per syllable, as
    produced by ``tone_context.plan_expected_tones``. A syllable with two
    acceptable realizations (這個's 個 as T4 or neutral) is credited with
    whichever matches better — realizing any accepted form is not an error.

    Deliberately does NOT apply ``apply_tone_sandhi``: the contextual layer has
    already decided what the surface targets are, and running the legacy rule
    over them again would rewrite those decisions.

    Returns ``[(score, matched_tone, provenance), ...]``. A real measurement is
    preferred over a placeholder constant even when the constant is
    numerically higher, since 75 for neutral tone is not evidence of anything.

    Windowing is shared with the legacy scorer via ``_window_for`` so the two
    always look at the same audio.
    """
    user_pitch = normalize_pitch_contour(pitch_contour)
    if len(user_pitch) == 0 or not accepted_tones:
        return []

    user_pitch = _smooth_for_directional_scoring(user_pitch)
    n = len(accepted_tones)
    syl_len = max(1, len(user_pitch) // n)
    windows = (
        syllable_windows
        if syllable_windows and len(syllable_windows) == n
        else None
    )

    results: List[Tuple[float, int, str]] = []
    for i, candidates in enumerate(accepted_tones):
        seg = user_pitch[slice(*_window_for(i, n, syl_len, len(user_pitch), windows))]
        best: Tuple[float, int, str] | None = None
        for tone in candidates or ():
            score, source = _score_segment(seg, tone)
            if best is None:
                best = (score, tone, source)
                continue
            measured_now = source == "measured"
            measured_best = best[2] == "measured"
            if (measured_now and not measured_best) or (
                measured_now == measured_best and score > best[0]
            ):
                best = (score, tone, source)
        results.append(best if best is not None else (0.0, 0, "not_scored"))
    return results


def _window_for(
    index: int,
    count: int,
    syl_len: int,
    total: int,
    windows: List[Tuple[int, int]] | None,
) -> Tuple[int, int]:
    """The (start, end) frame range one syllable is scored over.

    Extracted so the contextual scorer below splits the contour *exactly* the
    way the legacy one does. Getting this subtly wrong is not hypothetical: an
    earlier version scored one syllable at a time by passing a single-element
    tone list, which made the equal-split fallback treat the whole word as one
    syllable and hand every syllable in it the same score.
    """
    if windows is not None:
        return windows[index]
    start = index * syl_len
    end = start + syl_len if index < count - 1 else total
    return start, end


def _score_segment(seg: np.ndarray, tone: int) -> Tuple[float, str]:
    """Directional score for one syllable, with where the number came from.

    The single implementation behind both the legacy scorer and the contextual
    one, so the two can never drift apart.
    """

    if len(seg) < 4:
        # NOT a measurement. Kept because the legacy pass gate depends on it
        # (65 > 58, so an unmeasurable syllable currently passes), and
        # labelled so the diagnostic layer can refuse to use it.
        return 65.0, "constant_short_segment"  # too short to judge

    q = max(1, len(seg) // 4)  # quarter-length for regional means

    s_mean = float(np.mean(seg[:q]))         # start-region mean
    e_mean = float(np.mean(seg[-q:]))        # end-region mean
    mid_seg = seg[q: len(seg) - q]           # middle 50 %
    mid_min = float(np.min(mid_seg)) if len(mid_seg) else float(np.min(seg))
    variance = float(np.var(seg))

    if tone == 1:
        # Flat: low intra-syllable variance.
        # variance=0 → 100, variance≥0.12 → 0
        return max(0.0, 1.0 - variance / 0.12) * 100.0, "measured"

    if tone == 2:
        # Rising: end-region above start-region.
        # rise=+0.5 → 100, rise=0 → 50, rise=-0.5 → 0
        rise = e_mean - s_mean
        return max(0.0, min(1.0, (rise + 0.5) / 1.0)) * 100.0, "measured"

    if tone == 4:
        # Falling: start-region above end-region.
        fall = s_mean - e_mean
        return max(0.0, min(1.0, (fall + 0.5) / 1.0)) * 100.0, "measured"

    if tone == 3:
        # Dip: midpoint below the average of start and end regions.
        # dip_depth=+0.4 (deep V) → 100, dip_depth=0 (flat) → 45, negative → low
        avg_endpoints = (s_mean + e_mean) / 2.0
        dip_depth = avg_endpoints - mid_min
        return max(0.0, min(1.0, (dip_depth + 0.25) / 0.55)) * 100.0, "measured"

    # Neutral tone 5: short and light; no fixed pitch shape to grade. NOT a
    # measurement — there is no neutral-tone evaluator, so this constant says
    # nothing about how the learner spoke.
    return 75.0, "neutral_not_measured"


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

    Returns the mean of ``directional_tone_scores`` in [0, 100].
    """
    scores = directional_tone_scores(pitch_contour, tones)
    return float(np.mean(scores)) if scores else 0.0


def phrase_shape_curves(
    pitch_contour: List[Tuple[float, float]],
    tones: List[int],
    target_curve_override: List[float] | None = None,
) -> Tuple[List[float], List[float]]:
    """The exact pair of normalized curves ``calculate_phrase_shape_accuracy``
    compares — (user_curve, target_curve), both on the same [0, 1] scale and
    equal length.

    Exists so the UI can draw *literally the same two arrays the scorer
    scores* instead of re-deriving its own visual from raw Hz. The old
    overlay rescaled the idealized target into the student's own raw-Hz
    min/max band, which broke trust in both directions: a near-flat attempt
    squashed the target flat too (looked "matching", scored low), while one
    stray octave-error frame stretched the shared Hz range so a genuinely
    good attempt looked wrong (yet scored high, because scoring clips that
    outlier). Chart-visible similarity and the score can only agree if they
    consume the same normalized data — this function is that single source.

    ``target_curve_override``, when given, is a real model-voice reference
    curve (see ``praat_analyzer.reference_curve_for_span``) to compare
    against instead of the synthetic idealized tone-shape pattern. It must
    already be on ``normalize_pitch_contour``'s fixed 100-point [0, 1] scale
    (the same scale ``user_pitch`` below is always resampled to), so no
    further resampling is needed.

    Returns ([], []) when the contour or tone list can't produce a score
    (the same inputs for which the scorer returns 0.0).
    """
    if not pitch_contour or (not tones and not target_curve_override):
        return [], []

    user_pitch = normalize_pitch_contour(pitch_contour)
    if len(user_pitch) == 0:
        return [], []

    if target_curve_override:
        ref_pitch = target_curve_override
    else:
        ref_pitch = build_phrase_reference_pattern(apply_tone_sandhi(tones), num_points=len(user_pitch))
    return user_pitch.tolist(), np.asarray(ref_pitch).tolist()


def calculate_phrase_shape_accuracy(
    pitch_contour: List[Tuple[float, float]],
    tones: List[int],
    target_curve_override: List[float] | None = None,
) -> float:
    """Pure shape-similarity score against the reference contour for this
    tone sequence — correlation + distance, none of
    ``calculate_phrase_tone_accuracy``'s directional blending.

    Used wherever the UI shows a literal shape-overlay chart (the student's
    pitch drawn against the target curve, e.g. per-word practice cards) —
    the feedback text there should track that visual comparison directly,
    not the declination-robust blend tuned for whole-utterance
    scoring/gating in connected speech.

    Built on ``phrase_shape_curves`` so the score and any chart drawn from
    those curves can never disagree about what was compared. See
    ``phrase_shape_curves`` for ``target_curve_override``.
    """
    user_curve, target_curve = phrase_shape_curves(pitch_contour, tones, target_curve_override)
    if not user_curve:
        return 0.0

    return _shape_match_score(np.asarray(user_curve), np.asarray(target_curve))


# Shape-match weight in calculate_phrase_tone_accuracy's blend. Raised from
# the original 0.30 once the shape comparison could be sourced from a real
# model-voice recording instead of only a synthetic idealized tone-shape —
# a real reference is worth trusting more. Kept well short of 1.0 so a
# learner's own natural pace/declination against the directional check (see
# calculate_directional_tone_accuracy) still isn't unfairly penalized.
PHRASE_SHAPE_WEIGHT = 0.50
PHRASE_DIRECTIONAL_WEIGHT = 0.50


def calculate_phrase_tone_accuracy(
    pitch_contour: List[Tuple[float, float]],
    tones: List[int],
    target_curve_override: List[float] | None = None,
) -> float:
    """Score a pitch contour against the *expected* tone sequence for a word/phrase.

    Blends two complementary components:

    • Shape matching (``PHRASE_SHAPE_WEIGHT``) — correlation + distance
      against the reference contour (a real model-voice recording when
      ``target_curve_override`` is given, else the idealized synthetic
      tone-shape pattern); rewards students who nail the full tone shape in
      careful, isolated-word speech.

    • Directional scoring (``PHRASE_DIRECTIONAL_WEIGHT``) — checks only pitch
      *direction* per syllable (rising / falling / flat / dip). Robust to the
      declination, coarticulation and speaking-rate effects that distort tone
      shapes in natural connected speech — including pace differences from
      the reference recording — so a learner speaking fluently is not
      unfairly penalized.
    """
    if not pitch_contour or (not tones and not target_curve_override):
        return 0.0

    shape_score = calculate_phrase_shape_accuracy(pitch_contour, tones, target_curve_override)
    if target_curve_override:
        # Once a real teacher/TTS contour exists, the directional half must
        # not silently fall back to canonical synthetic tone templates. Use
        # the same reference-aware syllable comparison that the per-syllable
        # breakdown uses. This keeps word score, breakdown, and mastery on one
        # evidence source.
        reference_scores, _ = reference_syllable_scores(
            pitch_contour, tones, target_curve_override
        )
        directional_score = float(np.mean(reference_scores)) if reference_scores else 0.0
    else:
        directional_score = calculate_directional_tone_accuracy(pitch_contour, tones)

    return float(max(0.0, min(100.0, (
        shape_score * PHRASE_SHAPE_WEIGHT + directional_score * PHRASE_DIRECTIONAL_WEIGHT
    ))))


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
