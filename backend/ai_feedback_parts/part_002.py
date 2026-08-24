

async def generate_language_feedback(
    transcription: str,
    scene_prompt: str = "",
    scene_vocabulary: str = "",
    praat_tone_accuracy: float = 0,
    praat_fluency_score: float = 0,
    praat_vowel_quality: str = "",
    provider: str | None = None,
    image_b64: str | None = None,
    image_mime: str = "",
    scene_phrases: str = "",
    scene_suggested_answer: str = "",
    scene_attempt_number: int = 1,
) -> Dict:
    """Produce language feedback.

    ``provider`` overrides the env default per request ("local" | "gemini" |
    "openai"). The requested engine is tried first; if it lacks a key or the
    network call fails, we degrade gracefully to any other configured cloud
    provider and finally to the offline CAF engine, so the student always
    gets feedback. ``image_b64`` (the scene image) lets Gemini/OpenAI also
    judge whether what the student said actually matches what's pictured —
    Groq's text model has no vision input, so it's ignored there.
    """
    text = transcription.strip()
    args = (text, scene_prompt, scene_vocabulary, praat_tone_accuracy, praat_fluency_score, praat_vowel_quality)
    ref_kwargs = {
        "scene_phrases": scene_phrases,
        "scene_suggested_answer": scene_suggested_answer,
        "scene_attempt_number": scene_attempt_number,
    }
    if not text:
        return fallback_language_feedback(*args, image_b64=image_b64, **ref_kwargs)

    chosen = (provider or AI_FEEDBACK_PROVIDER or "local").strip().lower()
    if chosen == "local":
        return fallback_language_feedback(*args, image_b64=image_b64, **ref_kwargs)

    # Build priority order: chosen provider first, then others as fallback.
    all_providers = ["groq", "gemini", "openai"]
    order = [chosen] + [p for p in all_providers if p != chosen]
    callers = {
        "groq": _feedback_with_groq,
        "openai": _feedback_with_openai,
        "gemini": _feedback_with_gemini,
    }
    keys = {"groq": GROQ_API_KEY, "openai": OPENAI_API_KEY, "gemini": GEMINI_API_KEY}
    for name in order:
        if not keys.get(name):
            continue
        try:
            return await callers[name](*args, image_b64=image_b64, image_mime=image_mime, **ref_kwargs)
        except Exception as exc:
            print(f"{name} feedback failed, trying next engine: {exc}")

    return fallback_language_feedback(*args, image_b64=image_b64, **ref_kwargs)


async def _feedback_with_groq(
    transcription: str,
    scene_prompt: str = "",
    scene_vocabulary: str = "",
    praat_tone_accuracy: float = 0,
    praat_fluency_score: float = 0,
    praat_vowel_quality: str = "",
    image_b64: str | None = None,
    image_mime: str = "",
    scene_phrases: str = "",
    scene_suggested_answer: str = "",
    scene_attempt_number: int = 1,
) -> Dict:
    # Groq's text LLM has no vision input — content_accuracy falls back to the
    # offline placeholder regardless of whether an image was supplied.
    payload = {
        "model": GROQ_FEEDBACK_MODEL,
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an expert Mandarin (Traditional Chinese) speaking coach for Taiwanese learners. "
                    "Evaluate student speech honestly but encouragingly. "
                    "Always respond in valid JSON only — no markdown fences, no prose outside the JSON."
                ),
            },
            {
                "role": "user",
                "content": _feedback_prompt(
                    transcription, scene_prompt, scene_vocabulary, praat_tone_accuracy, praat_fluency_score, praat_vowel_quality,
                    scene_phrases=scene_phrases, scene_suggested_answer=scene_suggested_answer,
                    scene_attempt_number=scene_attempt_number,
                ),
            },
        ],
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json=payload,
        )

    if response.status_code != 200:
        raise RuntimeError(response.text)

    content = response.json()["choices"][0]["message"]["content"]
    data = json.loads(content)
    data["provider"] = "groq"
    feedback = _normalize_feedback(data, scene_attempt_number=scene_attempt_number, scene_suggested_answer=scene_suggested_answer)
    feedback["content_accuracy"] = _content_accuracy_placeholder(image_b64)
    return feedback


async def _feedback_with_openai(
    transcription: str,
    scene_prompt: str = "",
    scene_vocabulary: str = "",
    praat_tone_accuracy: float = 0,
    praat_fluency_score: float = 0,
    praat_vowel_quality: str = "",
    image_b64: str | None = None,
    image_mime: str = "",
    scene_phrases: str = "",
    scene_suggested_answer: str = "",
    scene_attempt_number: int = 1,
) -> Dict:
    prompt_text = _feedback_prompt(
        transcription, scene_prompt, scene_vocabulary, praat_tone_accuracy, praat_fluency_score, praat_vowel_quality,
        has_image=bool(image_b64),
        scene_phrases=scene_phrases, scene_suggested_answer=scene_suggested_answer,
        scene_attempt_number=scene_attempt_number,
    )
    user_content: list | str = prompt_text
    if image_b64:
        mime = image_mime or "image/png"
        user_content = [
            {"type": "text", "text": prompt_text},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
        ]

    payload = {
        "model": OPENAI_FEEDBACK_MODEL,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a Mandarin learning coach. Return only valid JSON with "
                    "provider, fluency, grammar, vocabulary, improved_version, and practice_prompt. "
                    "Keep feedback short, specific, and encouraging. Use Traditional Chinese examples when useful."
                ),
            },
            {
                "role": "user",
                "content": user_content,
            },
        ],
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json=payload,
        )

    if response.status_code != 200:
        raise RuntimeError(response.text)

    content = response.json()["choices"][0]["message"]["content"]
    data = json.loads(content)
    data["provider"] = "openai"
    return _normalize_feedback(data, scene_attempt_number=scene_attempt_number, scene_suggested_answer=scene_suggested_answer)


# Shared by the text and audio feedback prompts. Exists because the fields
# students actually read were coming back generic ("watch your tones",
# "good effort") — feedback a learner can't act on. Every rule here forces
# the model to anchor advice to something specific the student said and to
# phrase it for the app's audience: adult A1-A2 learners of Taiwan Mandarin.
_FEEDBACK_STYLE_RULES = """
Feedback style rules (apply to EVERY feedback / hint / practice_prompt string):
- Bilingual: one short Traditional Chinese sentence first (Taiwan usage — 臺灣華語 wording, e.g. 捷運 not 地鐵, 腳踏車 not 自行車), then " / " and a simple English version an A1-A2 learner can read.
- Anchor every point to a specific word the student actually said — quote it in 「」.
- pronunciation_note.feedback: name the exact syllable to fix and give ONE concrete vocal action (e.g. 「賣」: start high and fall firmly). When a tone was wrong, add one minimal pair to contrast, e.g. 買 mǎi (tone 3) vs 賣 mài (tone 4).
- Never give generic advice ("practice more", "watch your tones", "good job") — every sentence must contain a specific word, sound, or pattern the student can act on right now.
"""


def _audio_assessment_prompt(
    scene_prompt: str,
    vocab_line: str,
    praat_context: str,
    provider_tag: str,
    has_image: bool = False,
    reference_context: str = "",
    scene_attempt_number: int = 1,
) -> str:
    image_context = (
        "\nAn image is also attached. Judge content_accuracy by checking whether what the "
        "student said actually describes what's in the image — people, objects, setting, "
        "actions — not just whether the target words were said.\n"
        if has_image else ""
    )
    content_accuracy_block = (
        """,
  "content_accuracy": {
    "score": <int 0-100, 0 if no image was given>,
    "feedback": "<one sentence — if accepted, confirm what they got right; if NOT accepted, give a scaffolded hint pointing at which vocabulary word(s) or grammar slot to try, e.g. 'Try describing what the person is holding' or 'Use the 把 pattern to say what happened to the object' — never state or paraphrase the model answer itself>",
    "matched_details": [<things in the image the student correctly described>],
    "missed_details": [<things visible in the image the student did not mention or got wrong>],
    "accepted": <true if the sentence's meaning is an acceptable match for the scene (score >= 60), false otherwise>
  }"""
        if has_image else ""
    )
    reveal_now = scene_attempt_number > MAX_HINT_ATTEMPTS
    corrective_instructions = f"""
You are a tutor giving structured corrective feedback. This is attempt #{scene_attempt_number} on this picture.
Use the teacher's model answer (if provided above) as the coaching target:
1. Compare the student's sentence against the teacher's model — identify specific gaps: missing vocabulary, different grammar structure, content from the image not yet described.
2. {"Do NOT reveal the teacher's answer verbatim. Give a targeted hint naming the most important gap (e.g. missing word, wrong grammar slot, missing detail from the image) and ask the student to self-correct. Set reveal_answer to false and leave correct_version empty." if not reveal_now else "This is attempt 3 or later — the student has had two chances with hints. Now reveal the answer: set reveal_answer to true, fill correct_version with the teacher's model answer (or a fluent equivalent). In the hint field, briefly explain the 1-2 key differences between what the student said and the correct version so they understand what changed."}
"""

    return f"""Listen to this Mandarin audio recording and do two things:
1. Transcribe it exactly in Traditional Chinese (繁體中文).
2. Evaluate the student's speech using the context below.

Scene / task: {scene_prompt or "(open topic)"}
{vocab_line}{reference_context}{praat_context}{image_context}

IMPORTANT — evaluation order:
1. First judge MEANING: does the student's sentence make sense for this picture/scene, using the target vocabulary, grammar pattern, and model answer above as your standard? This is what content_accuracy and coherence capture.
2. Only treat pronunciation as worth detailed feedback if the meaning is acceptable (content_accuracy.accepted is true, or there's no image to judge against). Still score pronunciation_note from the Praat data either way — the app will decide whether to show it to the student.
{corrective_instructions}
Scoring guide:
- vocabulary_coverage.score: 0 = no target words used, 100 = all used
- coherence.score: 60 = acceptable grammar, 90+ = natural native-level
- pronunciation_note.score: use Praat tone accuracy if provided; 80+ = clear tones
{_FEEDBACK_STYLE_RULES}
Return ONLY this JSON (no markdown):
{{
  "transcription": "<exact Traditional Chinese transcript of the audio>",
  "provider": "{provider_tag}",
  "vocabulary_coverage": {{
    "score": <int 0-100>,
    "used": [<target words you heard the student say>],
    "missing": [<target words not heard>],
    "feedback": "<one sentence on which scene words were used and missed>"
  }},
  "coherence": {{
    "score": <int 0-100>,
    "feedback": "<one sentence — is the sentence grammatically complete and natural?>",
    "corrections": ["<short correction if needed, max 2>"]
  }},
  "pronunciation_note": {{
    "score": <int 0-100>,
    "feedback": "<one sentence citing specific tones or sounds to improve>"
  }}{content_accuracy_block},
  "corrective_feedback": {{
    "errors": [<short phrases marking the specific gap vs the teacher's model — e.g. "missing subject", "wrong verb" — never state the fix>],
    "hint": "{'<briefly explain 1-2 key differences between the student answer and the correct version, then confirm the correct version>' if reveal_now else '<name the single most important missing element compared to the teacher model — which word, pattern, or image detail — do NOT reveal the full answer>'}",
    "reveal_answer": {str(reveal_now).lower()},
    "correct_version": "{'<teacher model answer or fluent equivalent>' if reveal_now else ''}"
  }},
  "improved_version": "<a fluent Traditional Chinese sentence fitting the scene with the target vocabulary>",
  "practice_prompt": "<one concrete next step the student should try — a hint about vocabulary/grammar to use, not the finished sentence>"
}}"""


def _build_audio_context(
    scene_prompt: str,
    scene_vocabulary: str,
    praat_tone_accuracy: float,
    praat_fluency_score: float,
    praat_vowel_quality: str,
    scene_phrases: str = "",
    scene_suggested_answer: str = "",
) -> tuple[str, str, str]:
    """Return (vocab_line, praat_context, reference_context) strings for audio assessment prompts."""
    scene_words = [w.strip() for w in scene_vocabulary.split(",") if w.strip()]
    vocab_line = (
        f"Target vocabulary the student should use: {', '.join(scene_words)}."
        if scene_words else ""
    )
    praat_context = ""
    if praat_tone_accuracy > 0 or praat_fluency_score > 0:
        praat_context = (
            f"\nPraat acoustic data:\n"
            f"- Tone accuracy: {round(praat_tone_accuracy)}%\n"
            f"- Fluency score: {round(praat_fluency_score)}%"
        )
        if praat_vowel_quality:
            praat_context += f"\n- Vowel quality: {praat_vowel_quality}"

    reference_context = ""
    if scene_phrases.strip() or scene_suggested_answer.strip():
        reference_context = "\nCoaching reference (use to identify specific gaps between what the student said and what is expected):\n"
        if scene_phrases.strip():
            reference_context += f"- Target phrases to use: {scene_phrases.strip()}\n"
        if scene_suggested_answer.strip():
            reference_context += (
                f"- Teacher's model answer: {scene_suggested_answer.strip()}\n"
                "  Compare the student's sentence word-by-word against this model: which vocabulary words are missing, "
                "which grammar slots differ, and what content from the image is not yet described? "
                "Use these gaps to drive your corrective_feedback. Do NOT quote the model answer verbatim in hint "
                "fields on early attempts — instead name the specific missing element (word/pattern/content) so the "
                "student can self-correct.\n"
            )

    return vocab_line, praat_context, reference_context


def _unpack_audio_result(
    data: dict, provider_tag: str, scene_vocabulary: str = "", image_b64: str | None = None,
    scene_attempt_number: int = 1, scene_suggested_answer: str = "",
) -> dict:
    transcription = data.pop("transcription", "").strip()
    data["provider"] = provider_tag
    feedback = _normalize_feedback(data, scene_attempt_number=scene_attempt_number, scene_suggested_answer=scene_suggested_answer)
    # Silent recording — AI cannot reliably score what it didn't hear
    if not transcription:
        all_scene_words = [w.strip() for w in scene_vocabulary.split(",") if w.strip()]
        vc = feedback.get("vocabulary_coverage", {})
        vc["score"] = 0
        vc["used"] = []
        vc["missing"] = all_scene_words
        feedback["vocabulary_coverage"] = vc
    if "content_accuracy" not in feedback and image_b64:
        feedback["content_accuracy"] = _content_accuracy_placeholder(image_b64)
    return {"transcription": transcription, "feedback": feedback}


async def assess_audio_with_gemini(
    audio_bytes: bytes,
    scene_prompt: str = "",
    scene_vocabulary: str = "",
    praat_tone_accuracy: float = 0,
    praat_fluency_score: float = 0,
    praat_vowel_quality: str = "",
    image_b64: str | None = None,
    image_mime: str = "",
    scene_phrases: str = "",
    scene_suggested_answer: str = "",
    scene_attempt_number: int = 1,
) -> Dict:
    """Multimodal Gemini call: audio + image + vocabulary → transcription + feedback in one shot."""
    import base64
    audio_b64 = base64.b64encode(audio_bytes).decode()
    vocab_line, praat_context, reference_context = _build_audio_context(
        scene_prompt, scene_vocabulary, praat_tone_accuracy, praat_fluency_score, praat_vowel_quality,
        scene_phrases, scene_suggested_answer,
    )
    prompt = _audio_assessment_prompt(
        scene_prompt, vocab_line, praat_context, "gemini-audio", has_image=bool(image_b64),
        reference_context=reference_context, scene_attempt_number=scene_attempt_number,
    )

    content_parts: list = [
        {"inline_data": {"mime_type": "audio/wav", "data": audio_b64}},
        {"text": prompt},
    ]
    if image_b64:
        content_parts.append({"inline_data": {"mime_type": image_mime or "image/png", "data": image_b64}})

    payload = {
        "system_instruction": {
            "parts": [{"text": (
                "You are an expert Mandarin (Traditional Chinese) speaking coach. "
                "Listen carefully to the audio. Respond only with valid JSON."
            )}]
        },
        "contents": [{"parts": content_parts}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
            # gemini-3.6-flash "thinks" by default (1000+ hidden tokens on a
            # trivial extraction in testing), which risks tripping the
            # 20-30s timeouts below for latency-sensitive feedback calls
            # that don't need deep reasoning. Disabled, not just given a
            # longer timeout, since the extra thinking buys nothing here.
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_FEEDBACK_MODEL}:generateContent?key={GEMINI_API_KEY}",
            json=payload,
        )

    if response.status_code != 200:
        raise RuntimeError(response.text)

    raw = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    return _unpack_audio_result(
        json.loads(_strip_json_fence(raw)), "gemini-audio", scene_vocabulary, image_b64,
        scene_attempt_number=scene_attempt_number, scene_suggested_answer=scene_suggested_answer,
    )


async def assess_audio_with_openai(
    audio_bytes: bytes,
    scene_prompt: str = "",
    scene_vocabulary: str = "",
    praat_tone_accuracy: float = 0,
    praat_fluency_score: float = 0,
    praat_vowel_quality: str = "",
    image_b64: str | None = None,
    image_mime: str = "",
    scene_phrases: str = "",
    scene_suggested_answer: str = "",
    scene_attempt_number: int = 1,
) -> Dict:
    """Multimodal GPT-4o call: audio + image + vocabulary → transcription + feedback in one shot."""
    import base64
    audio_b64 = base64.b64encode(audio_bytes).decode()
    vocab_line, praat_context, reference_context = _build_audio_context(
        scene_prompt, scene_vocabulary, praat_tone_accuracy, praat_fluency_score, praat_vowel_quality,
        scene_phrases, scene_suggested_answer,
    )
    # gpt-4o-audio-preview doesn't accept image inputs, so content_accuracy
    # for this path falls back to the offline placeholder (handled below).
    prompt = _audio_assessment_prompt(
        scene_prompt, vocab_line, praat_context, "openai-audio", has_image=False,
        reference_context=reference_context, scene_attempt_number=scene_attempt_number,
    )

    user_content: list = [
        {
            "type": "input_audio",
            "input_audio": {"data": audio_b64, "format": "wav"},
        },
        {"type": "text", "text": prompt},
    ]

    payload = {
        "model": "gpt-4o-audio-preview",
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an expert Mandarin (Traditional Chinese) speaking coach. "
                    "Listen carefully to the audio. Respond only with valid JSON."
                ),
            },
            {
                "role": "user",
                "content": user_content,
            },
        ],
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json=payload,
        )

    if response.status_code != 200:
        raise RuntimeError(response.text)

    content = response.json()["choices"][0]["message"]["content"]
    return _unpack_audio_result(
        json.loads(content), "openai-audio", scene_vocabulary, image_b64,
        scene_attempt_number=scene_attempt_number, scene_suggested_answer=scene_suggested_answer,
    )
