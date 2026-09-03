_analysis_admission_lock = asyncio.Lock()
_analysis_waiters = 0


@asynccontextmanager
async def acquire_analysis_slot():
    """Admit a bounded number of CPU/ASR requests across all analysis routes."""
    global _analysis_waiters
    async with _analysis_admission_lock:
        if _analysis_waiters >= ANALYZE_QUEUE_LIMIT:
            raise HTTPException(
                status_code=503,
                detail="Analysis capacity is temporarily full. Please retry shortly.",
                headers={"Retry-After": "5"},
            )
        _analysis_waiters += 1

    counted_as_waiter = True
    try:
        async with analyze_semaphore:
            async with _analysis_admission_lock:
                _analysis_waiters -= 1
            counted_as_waiter = False
            yield
    finally:
        if counted_as_waiter:
            async with _analysis_admission_lock:
                _analysis_waiters -= 1


def apply_recording_qc_to_diagnostics(word_prosody: list, feedback_quality: dict) -> dict:
    """Gate every syllable diagnosis on recording quality, then summarize.

    QC answers "can this measurement be trusted?" and nothing else — it is
    never blended into a score. When the answer is no, each syllable's verdict
    is replaced by INVALID_AUDIO with the recording's own reason codes
    attached, because "record that again" is the honest response and "you said
    it wrong" is not.

    Mutates ``word_prosody`` in place (it is the same list going out on the
    response) and returns the sentence-level summary. The legacy ``passed``
    fields are left exactly as the analyzer produced them.
    """
    from tone_decision import DiagnosticStatus, QcEvidence, summarize_sentence

    quality = feedback_quality or {}
    evidence = QcEvidence(
        can_score_pronunciation=quality.get("can_score_pronunciation", True) is not False,
        reason_codes=tuple(quality.get("reason_codes") or ()),
    )
    recording_unusable = evidence.unusable_recording

    statuses = []
    for word in word_prosody or []:
        for syllable in word.get("syllables") or []:
            if "diagnostic_status" not in syllable:
                continue
            if recording_unusable:
                syllable["diagnostic_status"] = DiagnosticStatus.INVALID_AUDIO.value
                syllable["diagnostic_reason"] = "recording_quality_unusable"
                syllable["contour_match_score"] = None
            statuses.append(DiagnosticStatus(syllable["diagnostic_status"]))
        if recording_unusable and word.get("diagnostic_status"):
            word["diagnostic_status"] = DiagnosticStatus.INVALID_AUDIO.value

    summary = summarize_sentence(statuses)
    summary["recording_reason_codes"] = list(evidence.reason_codes)
    # Progression is untouched by any of the above and says so explicitly, so
    # nobody reading the payload has to infer which field drove the unlock.
    # TODO(calibration): whether UNCERTAIN should be allowed through the
    # progression gate must be decided from human-rater agreement data, not by
    # loosening it to raise pass rates.
    summary["controls_progression"] = False
    return summary


# Sentence-level gate: a recording passes when at least this fraction of
# its judged syllables passed. Engineering default, chosen to match the
# "students should be able to move on with occasional per-syllable
# imperfections" UX; not a calibrated cutoff.
SENTENCE_SYLLABLE_PASS_RATIO = float(
    os.getenv("SENTENCE_SYLLABLE_PASS_RATIO", "0.80")
)


def build_pronunciation_mastery(
    word_prosody: list,
    feedback_quality: dict,
    *,
    content_match: Optional[bool] = None,
    content_check_requested: bool = False,
    missing_target_units: Optional[list[str]] = None,
) -> dict:
    """Return one explicit, evidence-gated pronunciation verdict.

    The percentage is useful for progress history, but it cannot by itself
    answer the learner's practical question: "Did I pass this sentence?"
    This gate requires a passing verdict for every syllable that has enough
    pitch evidence to be judged. Short/unvoiced syllables are reported as
    unjudged instead of being turned into a false pronunciation fail, while a
    recording with no measurable syllables remains ``not_judged``.
    """
    quality = feedback_quality or {}
    missing_units = [unit for unit in (missing_target_units or []) if unit]
    # Keep missing content as one learner-facing phrase instead of exposing
    # every missing character as a separate practice item.
    missing_parts = ["".join(missing_units)] if missing_units else []
    if quality.get("can_score_pronunciation") is False:
        return {
            "passed": False,
            "status": "not_judged",
            "passed_syllables": 0,
            "total_syllables": 0,
            "failed_words": [],
            "practice_parts": missing_parts,
            "content_match": content_match,
            "missing_target_units": missing_units,
            "message": quality.get("student_message") or "Record again so the system can measure your tones.",
        }

    syllables = [
        syllable
        for word in word_prosody or []
        for syllable in word.get("syllables") or []
    ]

    def _is_counted_syllable(syllable: dict) -> bool:
        # Neutral tones and placeholder measurements have no reliable fixed
        # contour target. They remain visible in the diagnostic breakdown, but
        # must not affect the sentence-level numerator or denominator.
        if syllable.get("score_provenance") in {
            "neutral_not_measured",
            "not_scored",
            "constant_short_segment",
        }:
            return False
        return syllable.get("passed") is not None

    def _syllable_gate_passed(syllable: dict) -> bool:
        # UNCERTAIN is a measurement gap, not evidence of a tone mistake.
        # Only INCORRECT or INVALID_AUDIO costs the sentence pass. Neutral and
        # other placeholder syllables never reach this function because they
        # are excluded by _is_counted_syllable above.
        status = syllable.get("diagnostic_status")
        if status in ("INCORRECT", "INVALID_AUDIO"):
            return False
        if status is not None:
            return True
        return syllable.get("passed") is True

    judged_syllables = [syllable for syllable in syllables if _is_counted_syllable(syllable)]
    failed_words = []
    for word in word_prosody or []:
        word_syllables = word.get("syllables") or []
        if word_syllables:
            has_failure = any(
                _is_counted_syllable(syllable) and not _syllable_gate_passed(syllable)
                for syllable in word_syllables
            )
            # A measured UNCERTAIN syllable is not evidence of a mistake and
            # therefore must not lower the sentence pass rate. It is still a
            # useful optional practice signal, though: surface its word so the
            # learner can choose to repeat it. Placeholder UNCERTAIN rows such
            # as neutral tones remain excluded by _is_counted_syllable().
            has_optional_uncertain = any(
                _is_counted_syllable(syllable)
                and syllable.get("diagnostic_status") == "UNCERTAIN"
                for syllable in word_syllables
            )
            has_failure = has_failure or has_optional_uncertain
        else:
            # Preserve the legacy word-level fallback for payloads that do not
            # contain per-syllable rows.
            has_failure = word.get("passed") is False
        if has_failure and word.get("token"):
            failed_words.append(word["token"])

    if not judged_syllables:
        return {
            "passed": False,
            "status": "not_judged",
            "passed_syllables": 0,
            "total_syllables": 0,
            "failed_words": failed_words,
            "practice_parts": list(dict.fromkeys([*failed_words, *missing_parts])),
            "content_match": content_match,
            "missing_target_units": missing_units,
            "message": "Not enough measured tone evidence yet. Record the whole sentence again.",
        }

    passed_count = sum(_syllable_gate_passed(syllable) for syllable in judged_syllables)
    pronunciation_failed_words = list(failed_words)
    # Sentence-level pass rate: 80% of judged syllables suffices. Below that
    # the whole recording fails; above, the recording passes but the failed
    # words still surface in `failed_words` / `practice_parts` so a student
    # can optionally drill them without being forced to re-record the
    # entire sentence to move on.
    #
    # Kept as a named constant so a calibration pass can move it in one
    # place; matches the pattern used by SYLLABLE_PASS_THRESHOLD and the
    # word-level shape/direction thresholds in tone_decision.
    pass_rate = passed_count / len(judged_syllables)
    # content_match is not False (not "is True"): a null/unverified result
    # (the independent ASR check errored, timed out, or ran without a
    # configured model) fails open rather than blocking the pass — a
    # verification hiccup should never cost the student their pronunciation
    # pass. Only an explicit mismatch (False) blocks it. See the matching
    # fix in storyRecorderFeedback.ts's isContentAccepted/
    # sceneContentGatePassed — this function had the same bug.
    passed = pass_rate >= SENTENCE_SYLLABLE_PASS_RATIO and content_match is not False
    if content_match is False:
        missing_text = "".join(missing_units)
        content_message = "Say the complete target sentence before this attempt can pass."
        if missing_text:
            content_message += f" Missing: {missing_text}."
    elif content_check_requested and content_match is None:
        content_message = "We couldn't verify what was said. Record the target again."
    else:
        content_message = ""
    return {
        "passed": passed,
        "status": "passed" if passed else "needs_practice",
        "passed_syllables": passed_count,
        "total_syllables": len(judged_syllables),
        "failed_words": pronunciation_failed_words,
        "practice_parts": list(dict.fromkeys([*pronunciation_failed_words, *missing_parts])),
        "content_match": content_match,
        "missing_target_units": missing_units,
        "message": _mastery_message(
            passed=passed,
            passed_count=passed_count,
            total=len(judged_syllables),
            failed_words=pronunciation_failed_words,
            missing_parts=missing_parts,
            content_message=content_message,
        ),
    }


def _mastery_message(
    *,
    passed: bool,
    passed_count: int,
    total: int,
    failed_words: list,
    missing_parts: list,
    content_message: str,
) -> str:
    """Sentence-level mastery message.

    The 80% sentence-pass rule means a recording can pass while still
    having failed words the student may want to drill. Say so explicitly —
    "you can continue, and here is what to practise if you want" — rather
    than the old strict "all measured tones passed" copy, which would read
    as false to a learner staring at ✗ chips beside their words."""
    if passed:
        if failed_words:
            return (
                f"Passed ({passed_count}/{total} syllables counted for progress). "
                f"Practise {len(failed_words)} word(s) to sharpen your tones, "
                "or continue to the next scene."
            )
        return f"Passed ({passed_count}/{total} syllables counted for progress). You can continue."
    if content_message:
        return content_message
    highlighted = len(failed_words) or len(missing_parts) or 1
    return (
        f"Practise {highlighted} highlighted part(s), then record the "
        "whole sentence again."
    )


VOWEL_ZONE_LABELS = {
    ("high", "front"): "High front vowel — mouth nearly closed, tongue forward (like 你 nǐ)",
    ("high", "back"): "High back vowel — mouth nearly closed, lips rounded (like 書 shū)",
    ("mid", "front"): "Mid front vowel — tongue mid-high, forward (like 姐 jiě)",
    ("mid", "central"): "Mid central vowel — tongue in centre (like 的 de)",
    ("mid", "back"): "Mid back vowel — tongue mid, lips rounded (like 我 wǒ)",
    ("low", "central"): "Open vowel — mouth wide open, jaw dropped (like 啊 ā / 媽 mā)",
}


def classify_vowel_quality(formants: dict) -> str:
    """Translate the utterance's median F1/F2 into a plain-language label.

    Delegates the actual F1/F2 → articulatory-zone decision to
    ``vowel_analysis.vowel_zone``, which is the same function the per-syllable
    vowel readout uses. Sharing it is the point: a sentence-level label that
    disagreed with the per-character readout sitting right below it would be a
    bug the student can see.

    Note this is the *whole recording's* median, so it describes an average
    mouth position across every vowel said — useful as one line of context for
    the AI feedback, and no substitute for the per-syllable readout.
    """
    from vowel_analysis import vowel_zone

    zone = vowel_zone(formants.get("F1", 0), formants.get("F2", 0))
    if not zone:
        return ""
    return VOWEL_ZONE_LABELS.get((zone["height"], zone["backness"]), "")


def build_tone_direction(
    pitch_contour: list,
    detected_tone: int,
    tone_accuracy: float,
) -> str:
    """Return a plain-language description of the pitch movement the student produced."""
    if not pitch_contour or len(pitch_contour) < 3:
        return ""
    freqs = [p[1] for p in pitch_contour]
    start = float(np.mean(freqs[:max(1, len(freqs) // 5)]))
    end   = float(np.mean(freqs[-max(1, len(freqs) // 5):]))
    mid   = float(np.mean(freqs[len(freqs) // 3 : 2 * len(freqs) // 3]))
    delta = end - start
    dip   = (start + end) / 2 - mid  # positive = dip in middle

    tone_hints = {
        1: "Tone 1 should stay high and flat the whole time (→).",
        2: "Tone 2 should rise steadily from mid to high (↗).",
        3: "Tone 3 dips low in the middle then rises slightly (↘↗).",
        4: "Tone 4 should fall sharply from high to low (↘).",
    }

    if dip > 30:
        shape, arrow = "dips in the middle", "↘↗"
    elif delta > 25:
        shape, arrow = "rises", "↗"
    elif delta < -25:
        shape, arrow = "falls", "↘"
    else:
        shape, arrow = "stays roughly level", "→"

    quality = "Good match." if tone_accuracy >= 72 else "Needs more contrast."
    hint = tone_hints.get(detected_tone, "")
    return f"Your voice {shape} {arrow}. {quality} {hint}".strip()
