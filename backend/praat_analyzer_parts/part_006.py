

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
