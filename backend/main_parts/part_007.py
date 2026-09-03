

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


async def transcribe_with_auto_fallback(audio_content: bytes, vocab_hint: str = "") -> TranscriptionResponse:
    errors = []
    for provider in ASR_FALLBACK_ORDER:
        if provider == "gemini" and not GEMINI_API_KEY:
            errors.append("gemini: missing API key")
            continue
        if provider == "openai" and not OPENAI_API_KEY:
            errors.append("openai: missing API key")
            continue
        if provider == "groq" and not GROQ_API_KEY:
            errors.append("groq: missing API key")
            continue

        try:
            result = await transcribe_audio_content(audio_content, provider, vocab_hint=vocab_hint)
            if result.text.strip():
                return TranscriptionResponse(
                    text=result.text,
                    model=f"auto:{result.model}",
                )
            errors.append(f"{provider}: empty transcription")
        except Exception as exc:
            errors.append(f"{provider}: {exc}")

    # Every provider ran but heard nothing — that's silence or unclear
    # speech, not a server failure. Return empty so Praat still analyzes
    # the audio and the student gets an honest "no speech detected" rather
    # than a 503 error page.
    if errors and all(e.endswith(": empty transcription") for e in errors):
        logger.info("Auto ASR: every provider returned empty — silent or unclear audio")
        return TranscriptionResponse(text="", model="auto:silent")

    detail = (
        "No ASR provider produced a transcript. Tried: " + "; ".join(errors)
    )
    logger.error("Auto ASR failed. Errors: %s", errors)
    raise HTTPException(status_code=503, detail=detail)


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


VOCAB_POS_CODES = ["N", "V", "Adj", "Adv", "MW", "Particle", "Phrase", "Other"]


def _vocab_from_sentence_prompt(sentence: str) -> str:
    return f"""
You are helping a Taiwan Mandarin (國語/臺灣華語) teacher build a vocabulary table
for one sentence from a students' story.

Sentence:
{sentence}

Segment this sentence into its key vocabulary words (skip purely grammatical
particles that aren't useful vocabulary to study, but include meaningful
multi-character words as single words rather than splitting them into
individual characters). Return only valid JSON shaped exactly like:
[
  {{"word": "餐廳", "pinyin": "cāntīng", "pos": "N", "translation": "restaurant"}}
]

Rules:
- Every "word" must be an exact substring of the sentence, in Traditional Chinese.
- Do not repeat the same word twice.
- "pinyin" must use Taiwan Mandarin (國語) tone-marked pronunciation, e.g. "cāntīng".
- "pos" must be exactly one of: {", ".join(VOCAB_POS_CODES)}.
- "translation" is a short English translation (a few words at most).
- Return the JSON array only, no surrounding text.
"""


def _parse_vocab_words(data: object, sentence: str) -> List[VocabWordSuggestion]:
    if not isinstance(data, list):
        raise RuntimeError("Model did not return a JSON array of words")

    seen: set[str] = set()
    words: List[VocabWordSuggestion] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        word = str(item.get("word", "")).strip()
        if not word or word in seen or word not in sentence:
            continue
        seen.add(word)
        pos = str(item.get("pos", "")).strip()
        words.append(
            VocabWordSuggestion(
                word=word,
                pinyin=str(item.get("pinyin", "")).strip(),
                pos=pos if pos in VOCAB_POS_CODES else "",
                translation=str(item.get("translation", "")).strip(),
            )
        )
    return words


async def extract_vocab_from_sentence_with_groq(sentence: str) -> List[VocabWordSuggestion]:
    # Groq's JSON mode (like OpenAI's) only guarantees a top-level JSON
    # *object*, not a bare array, so the model is asked to wrap the array in
    # {"words": [...]}. This sidesteps the markdown-fence/stray-prose
    # failure mode entirely, unlike the Gemini path below.
    payload = {
        "model": GROQ_FEEDBACK_MODEL,
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a Taiwan Mandarin vocabulary-extraction assistant. "
                    "Always respond in valid JSON only — no markdown fences, no prose "
                    'outside the JSON. Wrap the array in a top-level object: {"words": [...]}.'
                ),
            },
            {"role": "user", "content": _vocab_from_sentence_prompt(sentence)},
        ],
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await _post_with_retry(client,
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json=payload,
        )

    if response.status_code != 200:
        raise RuntimeError(response.text)

    content = response.json()["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    data = parsed.get("words") if isinstance(parsed, dict) else parsed
    return _parse_vocab_words(data, sentence)


async def extract_vocab_from_sentence_with_gemini(sentence: str) -> List[VocabWordSuggestion]:
    payload = {"contents": [{"parts": [{"text": _vocab_from_sentence_prompt(sentence)}]}]}

    async with httpx.AsyncClient(timeout=30) as client:
        response = await _post_with_retry(client,
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_FEEDBACK_MODEL}:generateContent?key={GEMINI_API_KEY}",
            json=payload,
        )

    if response.status_code != 200:
        raise RuntimeError(response.text)

    content = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    data = json.loads(strip_json_fence(content))
    return _parse_vocab_words(data, sentence)


def _phrases_from_sentence_prompt(sentence: str, count: int) -> str:
    return f"""
You are helping a Taiwan Mandarin (國語/臺灣華語) teacher build a "handy phrases"
table for one sentence from a students' story — reusable multi-word
expressions or sentence patterns (not single vocabulary words, not the
whole sentence itself) that a student could reuse in other sentences.

Sentence:
{sentence}

Pick up to {count} of the most reusable phrase-level chunks from this
sentence. Return only valid JSON shaped exactly like:
[
  {{"phrase": "想要", "translation": "want to"}}
]

Rules:
- Every "phrase" must be an exact substring of the sentence, in Traditional
  Chinese, and at least two characters long.
- Do not repeat the same phrase twice.
- "translation" is a short English translation (a few words at most).
- Return the JSON array only, no surrounding text.
"""


def _parse_phrases(data: object, sentence: str) -> List[PhraseSuggestion]:
    if not isinstance(data, list):
        raise RuntimeError("Model did not return a JSON array of phrases")

    seen: set[str] = set()
    phrases: List[PhraseSuggestion] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        phrase = str(item.get("phrase", "")).strip()
        if not phrase or phrase in seen or phrase not in sentence:
            continue
        seen.add(phrase)
        phrases.append(
            PhraseSuggestion(
                phrase=phrase,
                translation=str(item.get("translation", "")).strip(),
            )
        )
    return phrases


async def extract_phrases_from_sentence_with_groq(
    sentence: str, count: int
) -> List[PhraseSuggestion]:
    payload = {
        "model": GROQ_FEEDBACK_MODEL,
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a Taiwan Mandarin phrase-extraction assistant. "
                    "Always respond in valid JSON only — no markdown fences, no prose "
                    'outside the JSON. Wrap the array in a top-level object: {"phrases": [...]}.'
                ),
            },
            {"role": "user", "content": _phrases_from_sentence_prompt(sentence, count)},
        ],
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await _post_with_retry(client,
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json=payload,
        )

    if response.status_code != 200:
        raise RuntimeError(response.text)

    content = response.json()["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    data = parsed.get("phrases") if isinstance(parsed, dict) else parsed
    return _parse_phrases(data, sentence)


async def extract_phrases_from_sentence_with_gemini(
    sentence: str, count: int
) -> List[PhraseSuggestion]:
    payload = {"contents": [{"parts": [{"text": _phrases_from_sentence_prompt(sentence, count)}]}]}

    async with httpx.AsyncClient(timeout=30) as client:
        response = await _post_with_retry(client,
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_FEEDBACK_MODEL}:generateContent?key={GEMINI_API_KEY}",
            json=payload,
        )

    if response.status_code != 200:
        raise RuntimeError(response.text)

    content = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    data = json.loads(strip_json_fence(content))
    return _parse_phrases(data, sentence)


def _vocab_distractors_prompt(words: List[VocabDistractorWord]) -> str:
    word_lines = "\n".join(
        f'{i + 1}. "{w.word}" -> "{w.translation}"'
        + (f' (used in: "{w.context}")' if w.context else "")
        + (f" (already used, do not repeat: {', '.join(w.avoid)})" if w.avoid else "")
        for i, w in enumerate(words)
    )
    return f"""
You are building multiple-choice distractors for a Mandarin vocabulary quiz.
For each word below, its correct English translation is already given.
Generate 3 WRONG but PLAUSIBLE English translations for each word — answers a
real student might mistakenly pick because they're close in meaning, the same
part of speech, or a common confusion (not random unrelated words).

Words:
{word_lines}

Return only valid JSON shaped exactly like:
[
  {{"word": "餐廳", "distractors": ["kitchen", "hotel", "cafeteria"]}}
]

Rules:
- "word" must exactly match one of the words given above.
- Each distractor must be different from that word's correct translation and
  from the other distractors for that word.
- A distractor must NOT be another acceptable translation of the word — the
  given correct translation must stay the ONLY correct option. If a
  candidate distractor could also be defended as a correct answer, replace
  it with a clearly wrong one.
- Distractors are short English translations (a few words at most), matching
  the style of the correct translation.
- Return the JSON array only, no surrounding text.
"""


def _parse_vocab_distractors(
    data: object, words: List[VocabDistractorWord]
) -> List[VocabDistractorResult]:
    if not isinstance(data, list):
        raise RuntimeError("Model did not return a JSON array of distractors")

    by_word = {w.word: w for w in words}
    results: List[VocabDistractorResult] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        word = str(item.get("word", "")).strip()
        source = by_word.get(word)
        if not source:
            continue
        correct = source.translation.strip().lower()
        seen = {correct}
        distractors: List[str] = []
        for raw in item.get("distractors", []):
            distractor = str(raw).strip()
            key = distractor.lower()
            if not distractor or key in seen:
                continue
            seen.add(key)
            distractors.append(distractor)
        if distractors:
            results.append(VocabDistractorResult(word=word, distractors=distractors[:3]))
    return results


async def generate_vocab_distractors_with_groq(
    words: List[VocabDistractorWord],
) -> List[VocabDistractorResult]:
    payload = {
        "model": GROQ_FEEDBACK_MODEL,
        "response_format": {"type": "json_object"},
        "temperature": 0.4,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a Mandarin vocabulary-quiz assistant. Always respond in "
                    "valid JSON only — no markdown fences, no prose outside the JSON. "
                    'Wrap the array in a top-level object: {"results": [...]}.'
                ),
            },
            {"role": "user", "content": _vocab_distractors_prompt(words)},
        ],
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await _post_with_retry(client,
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json=payload,
        )

    if response.status_code != 200:
        raise RuntimeError(response.text)

    content = response.json()["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    data = parsed.get("results") if isinstance(parsed, dict) else parsed
    return _parse_vocab_distractors(data, words)


async def generate_vocab_distractors_with_gemini(
    words: List[VocabDistractorWord],
) -> List[VocabDistractorResult]:
    payload = {"contents": [{"parts": [{"text": _vocab_distractors_prompt(words)}]}]}

    async with httpx.AsyncClient(timeout=30) as client:
        response = await _post_with_retry(client,
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_FEEDBACK_MODEL}:generateContent?key={GEMINI_API_KEY}",
            json=payload,
        )

    if response.status_code != 200:
        raise RuntimeError(response.text)

    content = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    data = json.loads(strip_json_fence(content))
    return _parse_vocab_distractors(data, words)


def _vocab_cloze_prompt(words: List[VocabClozeWord]) -> str:
    word_lines = "\n".join(
        f'{i + 1}. "{w.word}" -> "{w.translation}"'
        + (f' (style/level reference: "{w.context}")' if w.context else "")
        + (f" (already used, write a different sentence: {' / '.join(w.avoid)})" if w.avoid else "")
        for i, w in enumerate(words)
    )
    return f"""
You are building fill-in-the-blank (cloze) questions for an A1-A2 Mandarin
vocabulary quiz. For each word below, write ONE short, natural Traditional
Chinese sentence that uses that word — simple enough for a beginner, and
matching the style/vocabulary level of the reference sentence when one is
given. Also give 3 WRONG but PLAUSIBLE Chinese words that could grammatically
fill the same blank in that sentence (same part of speech, a real point of
confusion for a learner) — not random unrelated words.

Words:
{word_lines}

Return only valid JSON shaped exactly like:
[
  {{"word": "餐廳", "sentence": "我們今天要去餐廳吃飯。", "distractors": ["教室", "公園", "醫院"]}}
]

Rules:
- "word" must exactly match one of the words given above.
- "sentence" must contain that exact word, written naturally (not blanked out).
- Each distractor must be a different Chinese word from "word" and from the
  other distractors for that word, and must not itself appear in "sentence".
- Only "word" may correctly fill the blank: each distractor, placed in the
  blank, must make the sentence clearly wrong or unnatural. Never use a
  synonym of "word" or any word that would also produce a correct sentence.
- Return the JSON array only, no surrounding text.
"""
