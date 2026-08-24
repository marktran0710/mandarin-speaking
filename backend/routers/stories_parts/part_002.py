

@router.post("/api/custom-stories/{story_id}/generate-model-voice")
async def generate_model_voice(story_id: str, request: GenerateModelVoiceRequest):
    """Synthesizes this scene's model sentence via TTS and approximately
    slices each vocabulary word's own reference clip out of that one
    recording (see reference_voice.generate_scene_reference — edge-tts has
    no reliable word-boundary timing for Mandarin, so word clips are cut
    from the sentence audio rather than synthesized separately).

    Persists the sentence audio/script onto the existing
    listenAudioUrl/listenScript fields (tier-suffixed) and the new per-word
    audio URLs + cached reference pitch-shape curves onto
    vocabularyAudioUrls/vocabularyReferenceCurves (tier-suffixed) — the
    scoring engine (see chinese_tones.calculate_phrase_tone_accuracy) reads
    the cached curves back at analyze time via /api/analyze's
    scene_reference_curves field.

    Re-running this for a scene that already has a model voice replaces it
    and deletes the old audio files, rather than appending to the pool
    (unlike the vocabulary-* growth endpoints above) — there is exactly one
    model voice per scene/tier, not an accumulating candidate list.
    """
    tier = request.tier if request.tier in _TIER_SUFFIX else "easy"
    with connect_db() as db:
        frames = _load_frames(db, story_id)
        if request.frameIndex < 0 or request.frameIndex >= len(frames):
            raise HTTPException(status_code=404, detail="Frame not found.")
        frame = frames[request.frameIndex]

        sentence_text = (
            frame.get(_tier_field("listenScript", tier))
            or frame.get(_tier_field("suggestedAnswer", tier))
            or ""
        ).strip()
        if not sentence_text:
            raise HTTPException(
                status_code=422,
                detail="This scene has no suggested-answer or listen-script text to synthesize.",
            )
        vocab_text = frame.get(_tier_field("vocabulary", tier)) or ""
        words = [w.strip() for w in vocab_text.split(",") if w.strip()]

        try:
            result = await generate_scene_reference(
                story_id=story_id,
                frame_index=request.frameIndex,
                sentence_text=sentence_text,
                words=words,
                audio_dir=main.STORY_AUDIO_UPLOAD_DIR,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"Model-voice generation failed: {exc}"
            ) from exc

        # Clean up the previous generation's files before writing the new
        # ones, so re-generating doesn't leave orphaned audio behind.
        old_sentence_url = frame.get(_tier_field("listenAudioUrl", tier)) or ""
        main.remove_uploaded_file(old_sentence_url)
        for old_word_url in _existing_pool(frame, _tier_field("vocabularyAudioUrls", tier)):
            if isinstance(old_word_url, str):
                main.remove_uploaded_file(old_word_url)

        updates = {
            _tier_field("listenAudioUrl", tier): result["sentence_audio_url"],
            _tier_field("listenAudioSource", tier): "tts",
            _tier_field("listenScript", tier): result["sentence_script"],
            _tier_field("vocabularyAudioUrls", tier): json.dumps(
                [w["audio_url"] for w in result["words"]], ensure_ascii=False
            ),
            _tier_field("vocabularyReferenceCurves", tier): json.dumps(
                [w["curve"] for w in result["words"]]
            ),
            _tier_field("sentenceReferenceCurves", tier): json.dumps(
                result["sentence_reference_curves"], ensure_ascii=False
            ),
        }
        for field, value in updates.items():
            frame[field] = value
            _write_frame_field(db, story_id, request.frameIndex, field, value)

    return {"frameIndex": request.frameIndex, "tier": tier, **updates}


@router.post("/api/custom-stories/{story_id}/generate-model-voice-bulk")
async def generate_model_voice_bulk(story_id: str, request: GenerateModelVoiceBulkRequest):
    """Backfill tool: generates model voice for every frame of this story
    across the requested tiers, in place (reusing generate_model_voice
    above for each frame/tier). Scenes with no sentence text yet are
    skipped, and a single scene's TTS failure doesn't abort the rest of the
    story — every outcome is reported back instead.
    """
    with connect_db() as db:
        frame_count = len(_load_frames(db, story_id))

    results = []
    for frame_index in range(frame_count):
        for tier in request.tiers:
            if tier not in _TIER_SUFFIX:
                continue
            try:
                await generate_model_voice(
                    story_id, GenerateModelVoiceRequest(frameIndex=frame_index, tier=tier)
                )
                results.append({"frameIndex": frame_index, "tier": tier, "ok": True})
            except HTTPException as exc:
                results.append(
                    {"frameIndex": frame_index, "tier": tier, "ok": False, "detail": exc.detail}
                )
    return {"results": results}
