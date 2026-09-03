

def _parse_vocab_cloze(
    data: object, words: List[VocabClozeWord]
) -> List[VocabClozeResult]:
    if not isinstance(data, list):
        raise RuntimeError("Model did not return a JSON array of cloze results")

    by_word = {w.word: w for w in words}
    results: List[VocabClozeResult] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        word = str(item.get("word", "")).strip()
        source = by_word.get(word)
        if not source:
            continue
        # The model sometimes ignores the Traditional-Chinese instruction and
        # writes Simplified — convert before the containment check below,
        # since a Simplified sentence otherwise silently fails to contain a
        # Traditional-only word (e.g. "廳" not found in "厅") and the whole
        # candidate gets dropped.
        sentence = convert_to_traditional_chinese(str(item.get("sentence", "")).strip())
        if not sentence or word not in sentence:
            continue
        seen = {word}
        distractors: List[str] = []
        for raw in item.get("distractors", []):
            distractor = convert_to_traditional_chinese(str(raw).strip())
            if not distractor or distractor in seen or distractor in sentence:
                continue
            seen.add(distractor)
            distractors.append(distractor)
        if distractors:
            results.append(
                VocabClozeResult(word=word, sentence=sentence, distractors=distractors[:3])
            )
    return results


async def generate_vocab_cloze_with_groq(
    words: List[VocabClozeWord],
) -> List[VocabClozeResult]:
    payload = {
        "model": GROQ_FEEDBACK_MODEL,
        "response_format": {"type": "json_object"},
        "temperature": 0.6,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a Mandarin vocabulary-quiz assistant. Always respond in "
                    "valid JSON only — no markdown fences, no prose outside the JSON. "
                    'Wrap the array in a top-level object: {"results": [...]}.'
                ),
            },
            {"role": "user", "content": _vocab_cloze_prompt(words)},
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
    return _parse_vocab_cloze(data, words)


async def generate_vocab_cloze_with_gemini(
    words: List[VocabClozeWord],
) -> List[VocabClozeResult]:
    payload = {"contents": [{"parts": [{"text": _vocab_cloze_prompt(words)}]}]}

    async with httpx.AsyncClient(timeout=30) as client:
        response = await _post_with_retry(client,
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_FEEDBACK_MODEL}:generateContent?key={GEMINI_API_KEY}",
            json=payload,
        )

    if response.status_code != 200:
        raise RuntimeError(response.text)

    content = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    data = json.loads(strip_json_fence(content))
    return _parse_vocab_cloze(data, words)


def _vocab_synonym_prompt(words: List[VocabSynonymWord]) -> str:
    word_lines = "\n".join(
        f'{i + 1}. "{w.word}" -> "{w.translation}"'
        + (f' (used in: "{w.context}")' if w.context else "")
        + (f" (already used, give a different synonym: {' / '.join(w.avoid)})" if w.avoid else "")
        for i, w in enumerate(words)
    )
    return f"""
You are building "which word means the same?" questions for an A1-A2
Mandarin vocabulary quiz. For each word below, give ONE real Traditional
Chinese word or short phrase that is a close synonym — a beginner-level word
a student would recognize as meaning (nearly) the same thing. Also give 3
WRONG but PLAUSIBLE Chinese words that are NOT synonyms of the original word
(different meaning) but could look tempting — e.g. same topic/category or
same part of speech, a real point of confusion for a learner.

Words:
{word_lines}

Return only valid JSON shaped exactly like:
[
  {{"word": "高興", "synonym": "開心", "distractors": ["生氣", "累", "餓"]}}
]

Rules:
- "word" must exactly match one of the words given above.
- "synonym" must be a real word genuinely close in meaning to "word", and
  different from "word" itself.
- Each distractor must be a different Chinese word from "word", from
  "synonym", and from the other distractors for that word.
- Distractors must NOT be synonyms or near-synonyms of "word" — "synonym"
  must stay the ONLY option that means the same. If a candidate distractor
  is close enough in meaning to defend as correct, replace it with a
  clearly different one.
- Return the JSON array only, no surrounding text.
"""


def _parse_vocab_synonym(
    data: object, words: List[VocabSynonymWord]
) -> List[VocabSynonymResult]:
    if not isinstance(data, list):
        raise RuntimeError("Model did not return a JSON array of synonym results")

    by_word = {w.word: w for w in words}
    results: List[VocabSynonymResult] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        word = str(item.get("word", "")).strip()
        source = by_word.get(word)
        if not source:
            continue
        synonym = convert_to_traditional_chinese(str(item.get("synonym", "")).strip())
        if not synonym or synonym == word:
            continue
        seen = {word, synonym}
        distractors: List[str] = []
        for raw in item.get("distractors", []):
            distractor = convert_to_traditional_chinese(str(raw).strip())
            if not distractor or distractor in seen:
                continue
            seen.add(distractor)
            distractors.append(distractor)
        if distractors:
            results.append(
                VocabSynonymResult(word=word, synonym=synonym, distractors=distractors[:3])
            )
    return results


async def generate_vocab_synonym_with_groq(
    words: List[VocabSynonymWord],
) -> List[VocabSynonymResult]:
    payload = {
        "model": GROQ_FEEDBACK_MODEL,
        "response_format": {"type": "json_object"},
        "temperature": 0.6,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a Mandarin vocabulary-quiz assistant. Always respond in "
                    "valid JSON only — no markdown fences, no prose outside the JSON. "
                    'Wrap the array in a top-level object: {"results": [...]}.'
                ),
            },
            {"role": "user", "content": _vocab_synonym_prompt(words)},
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
    return _parse_vocab_synonym(data, words)


async def generate_vocab_synonym_with_gemini(
    words: List[VocabSynonymWord],
) -> List[VocabSynonymResult]:
    payload = {"contents": [{"parts": [{"text": _vocab_synonym_prompt(words)}]}]}

    async with httpx.AsyncClient(timeout=30) as client:
        response = await _post_with_retry(client,
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_FEEDBACK_MODEL}:generateContent?key={GEMINI_API_KEY}",
            json=payload,
        )

    if response.status_code != 200:
        raise RuntimeError(response.text)

    content = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    data = json.loads(strip_json_fence(content))
    return _parse_vocab_synonym(data, words)


async def generate_story_images_with_gemini(
    request: StoryImageGenerationRequest,
) -> StoryImageGenerationResponse:
    prompt = f"""
You are helping a Mandarin teacher create a six-picture speaking story.

Situation context:
{request.situation}

Student level:
{request.level}

Visual style:
{request.style}

Language focus:
{request.language_focus}

Return only valid JSON shaped exactly like:
{{
  "title": "short activity title",
  "learning_goal": "one sentence learning goal",
  "frames": [
    {{
      "title": "scene title",
      "student_prompt": "student speaking prompt",
      "vocabulary": ["word", "word", "word"],
      "image_prompt": "specific image generation prompt for one coherent story scene"
    }}
  ]
}}

Rules:
- Return exactly 6 frames.
- The 6 frames must tell one connected real-life story with clear narrative progression.
- Each frame shows ONE specific visible action — not just a place or object.
- image_prompt must be highly specific: describe the exact people (age, clothing, expression),
  their action (gesture, body language), the precise setting (specific location details,
  background objects), and the mood/lighting. Write it as a detailed scene description
  for a photorealistic image generator. Minimum 30 words per image_prompt.
  Example: "Photorealistic photo of a teenage Taiwanese girl in school uniform looking
  at her empty hands with a worried expression, standing on a Taipei MRT platform,
  other commuters visible in background, bright fluorescent station lighting."
- Do NOT use vague words like "scene", "illustration", "image of", "depicts".
- Use safe, real-life content appropriate for middle school students.
- Use Traditional Chinese vocabulary when useful, but keep JSON keys in English.
"""

    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    async with httpx.AsyncClient(timeout=30) as client:
        response = await _post_with_retry(client,
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_FEEDBACK_MODEL}:generateContent?key={GEMINI_API_KEY}",
            json=payload,
        )

    if response.status_code != 200:
        raise RuntimeError(response.text)

    content = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    data = json.loads(strip_json_fence(content))
    return await normalize_story_image_response(
        data,
        request,
        provider=GEMINI_FEEDBACK_MODEL,
    )


def build_story_image_fallback(
    request: StoryImageGenerationRequest,
    provider: str,
) -> StoryImageGenerationResponse:
    situation = request.situation.strip()
    title = title_from_situation(situation)
    scene_templates = [
        (
            "Set the scene",
            "Describe who is there and where the story begins.",
            ["who", "where", "today"],
        ),
        (
            "First action",
            "Tell what the main person does first.",
            ["first", "go", "meet"],
        ),
        (
            "Small problem",
            "Explain the problem or surprise in the situation.",
            ["problem", "because", "need"],
        ),
        (
            "Ask for help",
            "Say how someone asks, answers, or helps.",
            ["ask", "help", "together"],
        ),
        (
            "Solve it",
            "Describe what changes and how the problem is solved.",
            ["then", "finish", "better"],
        ),
        (
            "Ending feeling",
            "Finish the story with a feeling or lesson.",
            ["finally", "feel", "next time"],
        ),
    ]

    frames = []
    for index, (scene_title, prompt, vocabulary) in enumerate(scene_templates, start=1):
        image_prompt = (
            f"{request.style}, frame {index} of 6, {scene_title.lower()} for "
            f"the situation: {situation}. Show people doing a clear classroom-safe "
            "real-life action, consistent characters, soft colors, storybook composition."
        )
        frames.append(
            StoryImageFrame(
                index=index,
                title=scene_title,
                student_prompt=prompt,
                vocabulary=vocabulary,
                image_prompt=image_prompt,
                image_url=build_scene_svg_data_url(index, scene_title, situation),
            )
        )

    return StoryImageGenerationResponse(
        provider=provider,
        title=title,
        learning_goal=(
            "Students build a six-part Mandarin story by describing the scene, "
            "event, problem, help, solution, and feeling."
        ),
        frames=frames,
    )


async def generate_real_image(image_prompt: str, seed: int) -> str:
    """
    Download a real generated image and save it to uploads.
    Uses DALL-E 3 when OPENAI_API_KEY is set, otherwise Pollinations.ai (free).
    Returns a /uploads/images/... path on success, or "" on failure.
    """
    try:
        if OPENAI_API_KEY:
            payload = {
                "model": "dall-e-3",
                "prompt": image_prompt,
                "n": 1,
                "size": "1024x1024",
                "quality": "standard",
                "response_format": "url",
            }
            async with httpx.AsyncClient(timeout=45) as client:
                resp = await _post_with_retry(
                    client,
                    "https://api.openai.com/v1/images/generations",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    json=payload,
                )
            if resp.status_code != 200:
                raise RuntimeError(resp.text)
            img_url = resp.json()["data"][0]["url"]
        else:
            # Pollinations.ai — free, no key needed
            from urllib.parse import quote as url_quote
            encoded = url_quote(image_prompt)
            img_url = (
                f"https://image.pollinations.ai/prompt/{encoded}"
                f"?width=800&height=600&seed={seed}&model=flux&nologo=true"
            )

        # Download the image and save locally
        async with httpx.AsyncClient(timeout=60) as client:
            img_resp = await client.get(img_url, follow_redirects=True)
        if img_resp.status_code != 200:
            return ""

        content_type = img_resp.headers.get("content-type", "image/jpeg")
        ext = ".jpg" if "jpeg" in content_type else ".png"
        filename = f"gen-{seed}{ext}"
        path = os.path.join(IMAGE_UPLOAD_DIR, filename)
        with open(path, "wb") as f:
            f.write(img_resp.content)
        return f"/uploads/images/{filename}"
    except Exception as exc:
        logger.warning("Image generation failed (seed=%s): %s", seed, exc)
        return ""


async def normalize_story_image_response(
    data: dict,
    request: StoryImageGenerationRequest,
    provider: str,
) -> StoryImageGenerationResponse:
    fallback = build_story_image_fallback(request, provider=provider)
    raw_frames = data.get("frames", [])

    # Collect frame metadata first
    frame_meta = []
    for index in range(6):
        fallback_frame = fallback.frames[index]
        raw_frame = raw_frames[index] if index < len(raw_frames) and isinstance(raw_frames[index], dict) else {}
        title = str(raw_frame.get("title") or fallback_frame.title).strip()
        student_prompt = str(raw_frame.get("student_prompt") or fallback_frame.student_prompt).strip()
        vocabulary = raw_frame.get("vocabulary") or fallback_frame.vocabulary
        if not isinstance(vocabulary, list):
            vocabulary = fallback_frame.vocabulary
        raw_image_prompt = str(raw_frame.get("image_prompt") or fallback_frame.image_prompt).strip()
        # Enrich with realism instruction
        image_prompt = (
            f"Photorealistic scene, natural lighting, Taiwan setting. {raw_image_prompt} "
            f"No text overlays. Real people, real environment. Frame {index + 1} of a connected story."
        )
        frame_meta.append((index, title, student_prompt, vocabulary, image_prompt))

    # Generate all 6 images in parallel
    base_seed = abs(hash(request.situation)) % 100000
    image_urls = await asyncio.gather(*[
        generate_real_image(meta[4], base_seed + meta[0])
        for meta in frame_meta
    ])

    frames = []
    for (index, title, student_prompt, vocabulary, image_prompt), img_url in zip(frame_meta, image_urls):
        # Fall back to SVG placeholder only if image generation failed
        url = img_url or build_scene_svg_data_url(index + 1, title, request.situation)
        frames.append(StoryImageFrame(
            index=index + 1,
            title=title,
            student_prompt=student_prompt,
            vocabulary=[str(word) for word in vocabulary[:5]],
            image_prompt=image_prompt,
            image_url=url,
        ))

    return StoryImageGenerationResponse(
        provider=provider,
        title=str(data.get("title") or fallback.title).strip(),
        learning_goal=str(data.get("learning_goal") or fallback.learning_goal).strip(),
        frames=frames,
    )


def strip_json_fence(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```json"):
        return stripped.removeprefix("```json").removesuffix("```").strip()
    if stripped.startswith("```"):
        return stripped.removeprefix("```").removesuffix("```").strip()
    return stripped


def title_from_situation(situation: str) -> str:
    words = " ".join(situation.split()[:8])
    return f"{words} Story" if words else "Six Picture Story"
