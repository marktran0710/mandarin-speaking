

async def _do_analyze(
    content: bytes,
    transcription: str,
    asr_model: str,
    scene_prompt: str = "",
    scene_vocabulary: str = "",
    ai_provider: str = "",
    scene_image_url: str = "",
    scene_phrases: str = "",
    scene_suggested_answer: str = "",
    scene_attempt_number: int = 1,
    verify_word: str = "",
    pinyin_hint: str = "",
    reference_word_curves: Optional[Dict[str, list]] = None,
    scene_target_text: str = "",
    on_stage: Optional[Callable[[dict], None]] = None,
    # Optional attempt identity fields are retained for backward-compatible
    # clients; they do not enable a separate research or scoring path.
    participant_id: str = "",
    item_id: str = "",
    session_id: str = "",
    attempt_id: str = "",
    attempt_number: int = 1,
    attempt_type: str = "WHOLE_SENTENCE_INITIAL",
    study_phase: str = "",
) -> AnalysisResponse:
    tmp_path = None
    trace_started_at = time.perf_counter()
    trace_entries: list[dict[str, Any]] = []

    def add_trace_stage(
        stage: str,
        status: str,
        started_at: float,
        *,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        detail: Optional[str] = None,
        reason_codes: Optional[list[str]] = None,
        input: Optional[Dict[str, Any]] = None,
        output: Optional[Dict[str, Any]] = None,
    ) -> None:
        entry = {
            "stage": stage,
            "status": status,
            "duration_ms": round((time.perf_counter() - started_at) * 1000, 1),
            "model": model,
            "provider": provider,
            "detail": detail,
            "reason_codes": reason_codes or [],
            "input": input,
            "output": output,
        }
        trace_entries.append(entry)
        if on_stage is not None:
            on_stage(entry)

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
            tmp_file.write(content)
            tmp_path = tmp_file.name

        preflight_started_at = time.perf_counter()
        quality_target = verify_word.strip() or scene_target_text.strip() or scene_suggested_answer.strip()
        recording_preflight = assess_recording_quality(
            content,
            expected_syllable_count=_target_syllable_count(quality_target),
        )
        add_trace_stage(
            "preflight",
            recording_preflight.get("status", "review"),
            preflight_started_at,
            detail=recording_preflight.get("student_message") or recording_preflight.get("reason"),
            reason_codes=recording_preflight.get("reason_codes"),
            input={"audio_bytes": len(content)},
            output=recording_preflight,
        )
        transcription_model = ""
        ai_feedback = None
        image_b64, image_mime = await resolve_image_b64(scene_image_url) or (None, "")

        # For cloud AI providers that support audio input, send the recording +
        # vocabulary together so the model can directly hear which words were spoken.
        # Groq chains Whisper → LLaMA in one call (no audio LLM yet).
        # Falls back to the normal ASR → text → feedback path on any error.
        _audio_assessors = {
            "gemini": (GEMINI_API_KEY, "ai_feedback", "assess_audio_with_gemini", "gemini-audio"),
            "openai": (OPENAI_API_KEY, "ai_feedback", "assess_audio_with_openai", "openai-audio"),
            "groq":   (GROQ_API_KEY,   "ai_feedback", "assess_audio_with_groq",   "groq-audio"),
        }
        chosen_provider = (ai_provider or "").strip().lower()
        audio_assessed = False
        asr_started_at = time.perf_counter()
        if (
            recording_preflight["status"] != "retry"
            and not transcription.strip()
            and chosen_provider in _audio_assessors
        ):
            api_key, module, fn_name, tag = _audio_assessors[chosen_provider]
            if api_key:
                try:
                    import importlib
                    mod = importlib.import_module(module)
                    audio_result = await getattr(mod, fn_name)(
                        content, scene_prompt, scene_vocabulary,
                        image_b64=image_b64, image_mime=image_mime,
                        scene_phrases=scene_phrases, scene_suggested_answer=scene_suggested_answer,
                        scene_attempt_number=scene_attempt_number,
                    )
                    transcription = convert_to_traditional_chinese(audio_result["transcription"])
                    transcription_model = tag
                    ai_feedback = audio_result["feedback"]
                    audio_assessed = True
                    add_trace_stage(
                        "asr",
                        "integrated",
                        asr_started_at,
                        model=transcription_model,
                        provider=chosen_provider,
                        detail="Transcript and language feedback came from the audio provider.",
                        input={"audio_provider": chosen_provider, "scene_vocabulary": scene_vocabulary},
                        output={"transcription": transcription, "model": transcription_model},
                    )
                except Exception as exc:
                    logger.warning(f"{chosen_provider} audio assessment failed, falling back: {exc}")

        if not transcription.strip() and asr_model.strip():
            try:
                transcription_result = await transcribe_audio_content(
                    content, asr_model.strip(), vocab_hint=scene_vocabulary
                )
                transcription = transcription_result.text
                transcription_model = transcription_result.model
                add_trace_stage(
                    "asr",
                    "passed" if transcription.strip() else "review",
                    asr_started_at,
                    model=transcription_model,
                    detail="Backend transcription completed." if transcription.strip() else "ASR returned no transcript.",
                    input={"asr_model": asr_model.strip(), "scene_vocabulary": scene_vocabulary},
                    output={"transcription": transcription, "model": transcription_model},
                )
            except Exception as exc:
                add_trace_stage(
                    "asr", "failed", asr_started_at, model=asr_model.strip(), detail=str(exc),
                    input={"asr_model": asr_model.strip(), "scene_vocabulary": scene_vocabulary},
                )
                raise
        elif not trace_entries or trace_entries[-1]["stage"] != "asr":
            add_trace_stage(
                "asr",
                "skipped",
                asr_started_at,
                model=transcription_model or None,
                detail="Transcript was supplied by the caller.",
                input={"note": "Transcript was supplied by the caller, not transcribed."},
                output={"transcription": transcription, "model": transcription_model or None},
            )

        sentence_target = scene_target_text.strip() or scene_suggested_answer.strip()
        sentence_content_verified = bool(asr_model.strip() or transcription_model.strip())
        scene_content_match = None
        if (
            sentence_target
            and not verify_word.strip()
            and transcription.strip()
            and sentence_content_verified
        ):
            scene_content_match = _scene_content_match(sentence_target, transcription)

        # Use the known scene sentence for acoustic scoring unless the ASR
        # content check came back with a confirmed mismatch. See
        # _acoustic_scoring_source's docstring for why an unverified (None)
        # result must not fall back to the raw ASR transcript the same way a
        # real mismatch does — that used to silently cut the measured
        # syllable count for a correctly-spoken attempt.
        scoring_source = _acoustic_scoring_source(sentence_target, scene_content_match)
        if scoring_source == "scene_target":
            scoring_transcription = sentence_target
            scoring_pinyin_hint = pinyin_hint.strip() or canonical_pinyin(sentence_target)
        else:
            scoring_transcription = transcription
            scoring_pinyin_hint = (
                pinyin_hint.strip()
                if pinyin_hint.strip() and not sentence_target
                else canonical_pinyin(transcription)
            )

        # Scene vocabulary phrases arrive "; "-joined (see StoryRecorder.tsx)
        # since a scene can teach more than one multi-word phrase (e.g.
        # "這個週末; 做什麼"); split back out for the phrase-context rescue.
        target_phrases = [p.strip() for p in scene_phrases.split(";") if p.strip()]

        def _run_praat(path: str, tx: str):
            return analyze_all(
                path, tx, pinyin_hint=scoring_pinyin_hint,
                reference_word_curves=reference_word_curves,
                target_phrases=target_phrases,
            )

        # Run Praat (CPU-bound, threadpool), AI feedback (I/O-bound), and the
        # optional word-content verification pass all in parallel so checking
        # "did they actually say this word" doesn't add extra latency on top
        # of the analysis that was already happening.
        feedback_coro = (
            asyncio.sleep(0)  # no-op placeholder when feedback already done
            if audio_assessed or recording_preflight["status"] == "retry"
            else generate_language_feedback(
                transcription, scene_prompt, scene_vocabulary, provider=ai_provider or None,
                image_b64=image_b64, image_mime=image_mime,
                scene_phrases=scene_phrases, scene_suggested_answer=scene_suggested_answer,
                scene_attempt_number=scene_attempt_number,
            )
        )
        verify_coro = (
            _verify_word_transcription(content, verify_word, vocab_hint=scene_vocabulary)
            if verify_word.strip()
            else asyncio.sleep(0, result=(None, None))
        )
        praat_input = {
            "pinyin_hint": scoring_pinyin_hint or None,
            "scoring_text": scoring_transcription,
            "scoring_source": scoring_source,
            "reference_word_curves_provided": bool(reference_word_curves),
            "target_phrases": target_phrases or None,
        }

        async def run_praat_stage():
            started_at = time.perf_counter()
            try:
                result = await run_in_threadpool(_run_praat, tmp_path, scoring_transcription)
            except Exception as exc:
                add_trace_stage("praat", "failed", started_at, detail=str(exc), input=praat_input)
                raise
            (r_pitch_contour, r_formants, r_speech_rate, r_fluency_score, r_pitch_stats,
             r_word_prosody, r_detected_tone, r_tone_accuracy, _r_feedback,
             r_pause_analysis) = result
            add_trace_stage(
                "praat", "passed", started_at, detail="Acoustic analysis completed.",
                input=praat_input,
                output={
                    "pitch_contour": r_pitch_contour,
                    "formants": r_formants,
                    "speech_rate": r_speech_rate,
                    "fluency_score": r_fluency_score,
                    "pitch_statistics": r_pitch_stats,
                    "word_prosody": r_word_prosody,
                    "detected_tone": r_detected_tone,
                    "tone_accuracy": r_tone_accuracy,
                    "pause_analysis": r_pause_analysis,
                },
            )
            return result

        feedback_input = {
            "scene_prompt": scene_prompt or None,
            "scene_vocabulary": scene_vocabulary or None,
            "scene_phrases": scene_phrases or None,
            "scene_suggested_answer": scene_suggested_answer or None,
            "scene_attempt_number": scene_attempt_number,
            "image_provided": bool(image_b64),
        }

        async def run_feedback_stage():
            started_at = time.perf_counter()
            result = await feedback_coro
            output = result if isinstance(result, dict) else (ai_feedback if isinstance(ai_feedback, dict) else None)
            add_trace_stage(
                "feedback",
                "skipped" if audio_assessed or recording_preflight["status"] == "retry" else "passed",
                started_at,
                provider=(result.get("provider") if isinstance(result, dict) else None)
                or ai_provider
                or "backend-default",
                detail="Provider feedback completed." if not audio_assessed else "Audio provider feedback already included.",
                input=feedback_input,
                output=output,
            )
            return result

        async def run_verify_stage():
            started_at = time.perf_counter()
            result = await verify_coro
            if verify_word.strip():
                add_trace_stage(
                    "content_verification", "passed", started_at,
                    detail="Independent word verification completed.",
                    input={"verify_word": verify_word},
                    output={"recognized_text": result[0], "content_match": result[1]},
                )
            return result

        (praat_result, maybe_feedback, (recognized_text, content_match)) = await asyncio.gather(
            run_praat_stage(),
            run_feedback_stage(),
            run_verify_stage(),
        )
        if not audio_assessed:
            ai_feedback = maybe_feedback
        if sentence_target and not verify_word.strip():
            content_match = scene_content_match
            recognized_text = (transcription or None) if sentence_content_verified else None
            verification_started_at = time.perf_counter()
            add_trace_stage(
                "content_verification",
                "passed" if content_match is True else "review",
                verification_started_at,
                detail="Independent sentence ASR was compared with the scene target.",
                input={"target_text": sentence_target},
                output={
                    "recognized_text": recognized_text,
                    "content_match": content_match,
                    "asr_model": transcription_model or asr_model or None,
                },
            )
        content_target = verify_word.strip() or sentence_target
        recognized_for_diff = (
            recognized_text
            if verify_word.strip()
            else (transcription if sentence_content_verified else "")
        )
        content_diff = _scene_content_diff(content_target, recognized_for_diff or "")
        (pitch_contour, formants, speech_rate, fluency_score, pitch_stats,
         word_prosody, detected_tone, tone_accuracy, feedback,
         pause_analysis) = praat_result

        # No speech → noise from the mic can spuriously match a tone reference
        quality_started_at = time.perf_counter()
        feedback_quality = finalize_feedback_quality(
            recording_preflight,
            pitch_contour,
            transcription,
            content_match=content_match,
            content_was_verified=bool(verify_word.strip()) or sentence_content_verified,
        )
        add_trace_stage(
            "quality_gate",
            "passed" if feedback_quality["can_score_pronunciation"] else "retry",
            quality_started_at,
            detail=feedback_quality.get("student_message") or "Quality gate evaluated.",
            reason_codes=feedback_quality.get("reason_codes"),
            input={
                "preflight_status": recording_preflight.get("status"),
                "content_was_verified": bool(verify_word.strip()) or sentence_content_verified,
            },
            output=feedback_quality,
        )

        if not feedback_quality["can_score_pronunciation"]:
            tone_accuracy = 0
            detected_tone = 0
            fluency_score = 0.0
            feedback = feedback_quality["student_message"]
            for word in word_prosody:
                word["judged"] = False
                word["tone_accuracy"] = 0.0
                word["shape_accuracy"] = 0.0
                word["passed"] = None
                word["feedback"] = feedback_quality["student_message"]
                for syllable in word.get("syllables") or []:
                    syllable["score"] = 0.0
                    syllable["passed"] = None

        vowel_quality = classify_vowel_quality(formants)
        tone_direction = build_tone_direction(pitch_contour, detected_tone, tone_accuracy)

        # Turn the raw pause/rate measurements into judged, story-aggregatable
        # signals: how many pauses landed at a natural clause/punctuation
        # boundary in the reference script vs. mid-phrase ("choppy"), and the
        # articulation rate (syllables/sec, pauses excluded) for speed
        # feedback. Merged into pause_analysis so the frontend can pick these
        # up the same way it already reads pause_count/longest_pause.
        character_count = sum(1 for ch in scoring_transcription if "一" <= ch <= "鿿")
        fluency_for_response = caf_metrics.fluency_metrics(
            speech_rate, pause_analysis, character_count
        )
        # The teacher's listen script is the authoritative phrase-break source;
        # fall back to the suggested answer only for older scenes that have no
        # dedicated listen script.
        pause_reference_text = (
            scene_target_text.strip()
            or scene_suggested_answer.strip()
            or transcription
        )
        pause_judgment = caf_metrics.classify_pauses(
            pause_reference_text, pause_analysis, word_prosody
        )
        pause_analysis = {
            **pause_analysis,
            "articulation_rate": fluency_for_response["articulation_rate"],
            "choppy_pause_count": len(pause_judgment["choppy"]) if pause_judgment["judged"] else 0,
            "natural_pause_count": len(pause_judgment["natural"]) if pause_judgment["judged"] else 0,
        }

        # The parallel feedback call ran before Praat finished. Recompute the
        # local CAF feedback now that we have the acoustic numbers: when the
        # provider is local, swap in the full grounded result; for an external
        # provider, only patch its pronunciation_note with the real Praat data.
        from ai_feedback import (
            apply_feedback_quality_gate as _apply_feedback_quality_gate,
            fallback_language_feedback as _local_fb,
        )
        local_fb = _local_fb(
            transcription, scene_prompt, scene_vocabulary,
            praat_tone_accuracy=float(tone_accuracy),
            praat_fluency_score=float(fluency_score),
            praat_vowel_quality=vowel_quality or "",
            praat_pause_analysis=pause_analysis,
            praat_speech_rate=float(speech_rate),
            word_prosody=word_prosody,
            image_b64=image_b64,
            scene_phrases=scene_phrases,
            scene_suggested_answer=scene_suggested_answer,
            scene_attempt_number=scene_attempt_number,
        )
        if isinstance(ai_feedback, dict):
            if ai_feedback.get("provider") == "local":
                ai_feedback = local_fb
            else:
                ai_feedback["pronunciation_note"] = local_fb["pronunciation_note"]
        else:
            ai_feedback = local_fb
        ai_feedback = _apply_feedback_quality_gate(
            ai_feedback,
            feedback_quality,
            transcription=transcription,
            scene_vocabulary=scene_vocabulary,
        )
        description = build_analysis_description(scoring_transcription, transcription_model, word_prosody)

        # Recording-level QC is a gate on the *diagnostic* layer: when the
        # recording itself cannot support a judgement, no per-syllable verdict
        # may stand, however the contour happened to score. This deliberately
        # does not touch word_prosody[].passed — progression keeps running on
        # the legacy path exactly as before this patch.
        tone_diagnostics = apply_recording_qc_to_diagnostics(
            word_prosody, feedback_quality
        )
        pronunciation_mastery = build_pronunciation_mastery(
            word_prosody,
            feedback_quality,
            content_match=content_match,
            content_check_requested=bool(content_target),
            missing_target_units=(
                _missing_scene_content_units(content_target, recognized_for_diff or "")
                if content_match is False
                else []
            ),
        )

        # The optional research feedback layer is intentionally absent from
        # the classroom build. Keep the response field for compatibility with
        # older clients, but never compute or persist research-only data.
        assistive_feedback_result = None

        return AnalysisResponse(
            description=description,
            transcription=transcription,
            transcription_model=transcription_model,
            pitch_contour=pitch_contour,
            word_prosody=word_prosody,
            detected_tone=detected_tone,
            tone_accuracy=tone_accuracy,
            formants=formants,
            vowel_quality=vowel_quality,
            speech_rate=speech_rate,
            fluency_score=fluency_score,
            pitch_statistics=pitch_stats,
            tone_direction=tone_direction,
            pause_analysis=pause_analysis,
            feedback=feedback,
            ai_feedback=ai_feedback,
            recognized_text=recognized_text,
            content_match=content_match,
            content_diff=content_diff,
            feedback_quality=feedback_quality,
            tone_diagnostics=tone_diagnostics,
            pronunciation_mastery=pronunciation_mastery,
            assistive_feedback=assistive_feedback_result,
            processing_trace=ProcessingTrace(
                stages=[ProcessingTraceStage(**entry) for entry in trace_entries],
                total_duration_ms=round((time.perf_counter() - trace_started_at) * 1000, 1),
            ),
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
