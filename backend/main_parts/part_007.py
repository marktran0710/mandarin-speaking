

async def _verify_word_transcription(
    audio_content: bytes, word: str, vocab_hint: str = ""
) -> Tuple[Optional[str], Optional[bool]]:
    """Runs an independent ASR pass to check whether `word` was actually spoken.

    Word-practice callers pass the target word as the `transcription` so Praat
    scores tone against a known reference instead of a possibly-wrong ASR guess.
    That means tone scoring never actually confirms the student said the right
    word. This runs ASR for real, on the side, purely to catch that mismatch.
    Fails open (None, None) on ASR error so a transcription hiccup never blocks
    the pitch/tone feedback the student came for.

    `word` may be a single vocabulary word/character or, for phrase-practice
    callers, an entire multi-character phrase — requiring the whole string to
    appear verbatim was fine for short targets but made phrase verification
    fail outright whenever the independent ASR pass misheard a single
    syllable anywhere in a longer phrase (common, not rare). Longer targets
    use the same tolerant character-overlap ratio the frontend already
    applies for its own pass/fail verdict, so the two no longer disagree.

    Prefers Groq (fast, cloud) over the "auto" chain's default of the local
    ctwhisper model, which is CPU-heavy and — running alongside the Praat
    analysis on every single word attempt — made word practice noticeably
    slower once this check was added.
    """
    model = "groq" if GROQ_API_KEY else "auto"
    try:
        result = await transcribe_audio_content(audio_content, model, vocab_hint=vocab_hint or word)
        recognized = convert_to_traditional_chinese(result.text).strip()
        if not recognized:
            # ASR heard nothing — on a 1-2s single-syllable drill clip
            # that's an ASR limitation, not evidence the wrong word was
            # spoken. Unverifiable (None), the same fail-open contract as
            # an ASR error; a hard False here silently blocked passing
            # drills from ever clearing their mastery chip.
            return recognized, None
        return recognized, _scene_content_match(word, recognized)
    except Exception as exc:
        logger.warning("Word content verification failed: %s", exc)
        return None, None


def build_analysis_description(
    transcription: str,
    transcription_model: str,
    word_prosody: list[dict],
) -> str:
    text = transcription.strip()
    word_count = len(word_prosody)

    if not text:
        return (
            "The audio was analyzed for pitch and fluency, but no transcript was "
            "returned. Try a clearer recording with one short sentence."
        )

    model_note = (
        f" using {transcription_model}"
        if transcription_model
        else ""
    )
    return (
        f"The system transcribed your recording{model_note} and found "
        f"{word_count} word-level prosody item{'s' if word_count != 1 else ''} "
        "for review."
    )
