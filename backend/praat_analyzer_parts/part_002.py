

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

    Selected by TONE_ALIGNER so deployments can choose the supported
    syllable-alignment strategy without changing the analyzer code.
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


# Syllable diagnoses whose UNCERTAIN comes from having no real measurement
# (short segment / neutral tone / not scored) rather than ambiguous evidence
# — these must never be treated as evidence for a promotion, and must never
# silently inherit a word-level pass. Shared by `_combine_word_verdict` and
# the passed-propagation step right after it in `estimate_word_prosody`.
_PLACEHOLDER_SCORE_PROVENANCES = {
    "constant_short_segment",
    "neutral_not_measured",
    "not_scored",
}
