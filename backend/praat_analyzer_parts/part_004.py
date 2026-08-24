

def estimate_word_prosody(
    pitch_contour: List[Tuple[float, float]],
    transcription: str = "",
    pinyin_hint: str = "",
    reference_word_curves: Dict[str, List[float]] | None = None,
    intensity: List[Tuple[float, float]] | None = None,
    sound=None,
    target_phrases: List[str] | None = None,
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
    ``target_phrases``: optional teacher-designated phrases for this scene
    (e.g. ``["這個週末"]``). When one spans more than one jieba word, see
    ``_apply_phrase_rescue`` — a syllable/word that measured INCORRECT on its
    own can be promoted if the combined phrase span clears a stricter bar.
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
    syllable_spans = _aligner().align(pitch_contour, total_chars, intensity)
    use_spans = len(syllable_spans) == total_chars
    vowel_records: List[Dict] | None = (
        _syllable_vowels(sound, syllable_spans, tokens)
        if sound is not None and use_spans
        else None
    )
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
        _ONSET_SKIP = 0.12
        onset_threshold = segment_start + (segment_end - segment_start) * _ONSET_SKIP
        scoring_points = [p for p in points if p[0] >= onset_threshold] or points
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
            syllable_scores = [0.0] * len(expected_tones)
        else:
            tone_score = 0.0
            shape_score = 0.0
        is_content = _classify_content_word(token)
        syllables: List[Dict] = []
        if is_chinese and syllable_scores and len(expected_tones) == len(token):
            syllables = [
                {
                    "char": token[i],
                    "tone": expected_tones[i],
                    "score": round(score, 1),
                    "passed": None,
                }
                for i, score in enumerate(syllable_scores)
            ]
            for i, entry in enumerate(syllables):
                record = None
                if vowel_records is not None:
                    global_index = consumed - token_chars + i
                    if 0 <= global_index < len(vowel_records):
                        record = vowel_records[global_index]
                entry.update(record or {"vowel_status": "not_measured"})
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
                diagnostic_status = entry.get("diagnostic_status")
                if not segment_judged:
                    entry["passed"] = None
                elif diagnostic_status:
                    entry["passed"] = diagnostic_status == DiagnosticStatus.CORRECT.value
                else:
                    entry["passed"] = entry["legacy"]["passed"]
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
        final_word_status, word_reason = _combine_word_verdict(word_decision, syllables)
        word_diagnostic = final_word_status.value
        if final_word_status is DiagnosticStatus.CORRECT and segment_judged:
            for entry in syllables:
                if entry.get("score_provenance") in _PLACEHOLDER_SCORE_PROVENANCES:
                    continue
                if entry.get("passed") is not True:
                    entry["passed"] = True
        if not segment_judged:
            word_passed = None
        else:
            word_passed = final_word_status == DiagnosticStatus.CORRECT
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
                "shape_score": round(shape_score, 1) if segment_judged else None,
                "direction_score": (
                    round(direction_score, 1) if segment_judged else None
                ),
                "display_score": word_decision.display_score,
                "verdict": word_diagnostic,
                "reason": word_reason,
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
    all_pitches = [s["mean_pitch"] for s in segments if s["mean_pitch"] > 0]
    utterance_mean = float(np.mean(all_pitches)) if all_pitches else 0.0
    if utterance_mean > 0:
        for seg in segments:
            seg["prominence_score"] = round(
                (seg["mean_pitch"] - utterance_mean) / utterance_mean, 3
            )
    _apply_phrase_rescue(segments, target_phrases)
    return segments
