

def _combine_word_verdict(word_decision, syllables: list) -> tuple:
    """Combine the word-level shape+direction verdict with per-syllable
    diagnoses into the word's final status and a reason that always
    describes THAT final status.

    ``word_decision.reason`` explains the word-level shape/direction
    decision alone (e.g. "strong_shape_supported"). When the min-rule
    safety net or a syllable-rollup promotion below overrides that
    decision, the original reason becomes actively misleading — a word can
    end up INCORRECT while still carrying "strong_shape_supported", which
    reads as justification for a CORRECT verdict. This resolves the reason
    to match whichever status actually wins.

    Ordinarily the min-rule is absolute: one INCORRECT syllable fails the
    word no matter how strong the whole-word shape/direction look, because a
    genuine tone error usually shows up in both readings. But when the
    whole-word evidence clears PHRASE_RESCUE_SHAPE_STRONG /
    PHRASE_RESCUE_DIRECTION_SUPPORT — the same stricter bar
    `_apply_phrase_rescue` requires to override an individually-measured
    INCORRECT syllable across a word boundary — that evidence is strong
    enough to make the same claim within a single word (e.g. 週末 measured
    shape=93/direction=94 while 末 alone read INCORRECT). This mutates the
    overridden syllable(s) in place — flipping `diagnostic_status`/`passed`
    and attaching a `word_rescue` evidence dict — so the row is never left
    showing "Likely tone mismatch" for a syllable now counted as passed.
    """
    from tone_decision import (
        DiagnosticStatus,
        PHRASE_RESCUE_DIRECTION_SUPPORT,
        PHRASE_RESCUE_SHAPE_STRONG,
        aggregate_word,
    )

    has_placeholder_uncertain = any(
        entry.get("diagnostic_status") == DiagnosticStatus.UNCERTAIN.value
        and entry.get("score_provenance") in _PLACEHOLDER_SCORE_PROVENANCES
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
    syllable_statuses = [
        DiagnosticStatus(entry["diagnostic_status"])
        for entry in syllables
        if entry.get("diagnostic_status")
    ]
    syllable_rollup = aggregate_word(syllable_statuses) if syllable_statuses else None

    overrides_incorrect_syllable = (
        has_incorrect_syllable
        and word_decision.status is DiagnosticStatus.CORRECT
        and (word_decision.shape_score or 0) >= PHRASE_RESCUE_SHAPE_STRONG
        and (word_decision.direction_score or 0) >= PHRASE_RESCUE_DIRECTION_SUPPORT
    )

    if word_decision.status is DiagnosticStatus.INVALID_AUDIO or has_invalid_syllable:
        final_status = DiagnosticStatus.INVALID_AUDIO
    elif has_incorrect_syllable and not overrides_incorrect_syllable:
        final_status = DiagnosticStatus.INCORRECT
    elif word_decision.status is DiagnosticStatus.CORRECT and not has_placeholder_uncertain:
        final_status = DiagnosticStatus.CORRECT
    elif syllable_rollup is DiagnosticStatus.CORRECT:
        final_status = DiagnosticStatus.CORRECT
    elif syllable_rollup is not None:
        final_status = syllable_rollup
    else:
        final_status = word_decision.status

    if final_status is DiagnosticStatus.CORRECT and overrides_incorrect_syllable:
        for entry in syllables:
            if entry.get("diagnostic_status") != DiagnosticStatus.INCORRECT.value:
                continue
            entry["word_rescue"] = {
                "shape_score": word_decision.shape_score,
                "direction_score": word_decision.direction_score,
                "promoted_from": "INCORRECT",
            }
            entry["diagnostic_status"] = DiagnosticStatus.CORRECT.value
            entry["diagnostic_reason"] = "word_shape_direction_overrides_syllable"
            entry["passed"] = True
        reason = "exceptionally_strong_shape_overrides_incorrect_syllable"
    elif final_status is word_decision.status:
        reason = word_decision.reason
    elif final_status is DiagnosticStatus.INCORRECT:
        reason = "incorrect_syllable_overrides_word_shape"
    elif final_status is DiagnosticStatus.INVALID_AUDIO:
        reason = "invalid_syllable_overrides_word_shape"
    elif final_status is DiagnosticStatus.CORRECT:
        reason = "syllable_rollup_promoted_to_correct"
    else:
        reason = f"syllable_rollup_{final_status.value.lower()}"

    return final_status, reason
