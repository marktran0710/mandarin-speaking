

def _clean_target_phrases(raw: List[str] | None) -> List[str]:
    """Normalize a caller-supplied phrase list into distinct, meaningful
    entries: strip whitespace, drop empties/dupes, and drop anything with no
    Hanzi (nothing for the tone scorer to re-check)."""
    if not raw:
        return []
    cleaned: List[str] = []
    seen = set()
    for phrase in raw:
        text = (phrase or "").strip()
        if not text or text in seen or not re.search(r"[一-鿿]", text):
            continue
        seen.add(text)
        cleaned.append(text)
    return cleaned


def _find_contiguous_token_run(
    tokens: List[str], phrase: str
) -> Tuple[int, int] | None:
    """First contiguous run of ``tokens`` whose concatenation equals
    ``phrase``, as a ``(start, end)`` half-open range — or ``None``."""
    for start in range(len(tokens)):
        joined = ""
        for end in range(start, len(tokens)):
            joined += tokens[end]
            if joined == phrase:
                return start, end + 1
            if len(joined) >= len(phrase):
                break
    return None


def _apply_phrase_rescue(
    segments: List[Dict], target_phrases: List[str] | None
) -> None:
    """Re-score a designated target phrase (e.g. teacher vocabulary "這個
    週末") as one combined span when jieba split it into separate words that
    were scored — and one of them failed — independently.

    Word-boundary slicing can cut a syllable's pitch window at a point that
    distorts its measured contour (coarticulation from the neighboring word,
    an alignment snap that lands slightly wrong) even when the syllable was
    actually produced correctly. Re-scoring the combined span the teacher
    actually taught as one unit gives that syllable a second, wider-context
    reading.

    This is a rescue, never a downgrade: it only ever moves a syllable/word
    toward CORRECT, and only when the combined-phrase evidence clears
    PHRASE_RESCUE_SHAPE_STRONG / PHRASE_RESCUE_DIRECTION_SUPPORT — bars
    stricter than the normal per-word promotion, because overriding an
    individually-measured INCORRECT syllable (which the ordinary min-rule
    never allows) is a stronger claim than a normal promotion. Placeholder
    syllables (neutral tone / too short to measure) and any run touching
    INVALID_AUDIO are exempt, mirroring the same exemptions
    `_combine_word_verdict` applies at the word level. Mutates `segments` in
    place; returns nothing.
    """
    phrases = _clean_target_phrases(target_phrases)
    if not phrases or len(segments) < 2:
        return

    from chinese_tones import calculate_directional_tone_accuracy, calculate_phrase_shape_accuracy
    from tone_decision import (
        DiagnosticStatus,
        PHRASE_RESCUE_DIRECTION_SUPPORT,
        PHRASE_RESCUE_SHAPE_STRONG,
        aggregate_word,
    )

    tokens = [seg["token"] for seg in segments]
    for phrase in phrases:
        run = _find_contiguous_token_run(tokens, phrase)
        if run is None:
            continue
        start, end = run
        if end - start < 2:
            continue  # already a single jieba token; nothing to merge

        run_segments = segments[start:end]
        run_syllables = [
            syllable
            for seg in run_segments
            for syllable in seg.get("syllables") or []
        ]
        if not run_syllables:
            continue
        if any(
            s.get("diagnostic_status") == DiagnosticStatus.INVALID_AUDIO.value
            for s in run_syllables
        ):
            continue  # wider context cannot fix an unusable recording
        if all(
            s.get("diagnostic_status") == DiagnosticStatus.CORRECT.value
            for s in run_syllables
        ):
            continue  # nothing to rescue

        merged_contour = [
            point for seg in run_segments for point in seg.get("pitch_contour") or []
        ]
        merged_tones = [s["tone"] for s in run_syllables]
        if len(merged_contour) < 4:
            continue

        shape = calculate_phrase_shape_accuracy(merged_contour, merged_tones)
        direction = calculate_directional_tone_accuracy(merged_contour, merged_tones)
        if shape < PHRASE_RESCUE_SHAPE_STRONG or direction < PHRASE_RESCUE_DIRECTION_SUPPORT:
            continue

        evidence = {
            "phrase": phrase,
            "shape_score": round(shape, 1),
            "direction_score": round(direction, 1),
        }
        for syllable in run_syllables:
            if syllable.get("score_provenance") in _PLACEHOLDER_SCORE_PROVENANCES:
                continue
            if syllable.get("diagnostic_status") == DiagnosticStatus.CORRECT.value:
                continue
            syllable["phrase_rescue"] = {
                **evidence,
                "promoted_from": syllable.get("diagnostic_status"),
            }
            syllable["diagnostic_status"] = DiagnosticStatus.CORRECT.value
            syllable["diagnostic_reason"] = "phrase_context_rescued"
            syllable["passed"] = True

        for seg in run_segments:
            seg_syllables = seg.get("syllables") or []
            if not seg_syllables:
                continue
            seg_status = aggregate_word(
                [DiagnosticStatus(s["diagnostic_status"]) for s in seg_syllables]
            )
            if (
                seg_status is DiagnosticStatus.CORRECT
                and seg.get("verdict") != DiagnosticStatus.CORRECT.value
            ):
                seg["verdict"] = DiagnosticStatus.CORRECT.value
                seg["diagnostic_status"] = DiagnosticStatus.CORRECT.value
                seg["reason"] = "phrase_context_rescued"
                seg["passed"] = True


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
