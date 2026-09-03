

@router.post("/api/vocab-quiz-synonym", response_model=VocabSynonymResponse)
async def vocab_quiz_synonym(request: VocabSynonymRequest, req: Request):
    """
    Generate "which word means the same?" questions for the vocabulary quiz:
    a real Chinese synonym per word plus plausible non-synonym distractors —
    another alternative question shape mixed in alongside translation/cloze.
    """
    client_ip = req.client.host if req.client else "unknown"
    main._check_rate_limit(f"vocab-quiz-synonym:{client_ip}", max_requests=10, window_seconds=60)

    words = [w for w in request.words if w.word.strip() and w.translation.strip()]
    if not words:
        raise HTTPException(status_code=400, detail="Provide at least one word with a translation.")

    engines = [
        ("groq", main.GROQ_API_KEY, main.generate_vocab_synonym_with_groq),
        ("gemini", main.GEMINI_API_KEY, main.generate_vocab_synonym_with_gemini),
    ]
    if not any(key for _, key, _ in engines):
        raise HTTPException(
            status_code=503,
            detail="AI synonym generation requires GROQ_API_KEY or GEMINI_API_KEY to be configured on the backend.",
        )

    last_error: Exception | None = None
    for name, key, generate in engines:
        if not key:
            continue
        try:
            results = await generate(words)
        except Exception as exc:
            main.logger.warning("%s synonym generation failed, trying next engine: %s", name, exc)
            last_error = exc
            continue
        return VocabSynonymResponse(results=results)

    raise HTTPException(
        status_code=502,
        detail="Could not generate synonym questions for these words.",
    ) from last_error
