

async def assess_audio_with_groq(
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
    """Groq two-step pipeline: Whisper ASR + LLaMA feedback in one function.

    Groq's LLM API doesn't accept audio input yet, so we chain:
    audio → Groq whisper-large-v3 (transcription) → Groq LLaMA (feedback)
    Both calls share the same vocabulary context. Groq's LLaMA has no vision
    input, so content_accuracy falls back to the offline placeholder.
    """
    scene_words = [w.strip() for w in scene_vocabulary.split(",") if w.strip()]
    vocab_hint = ", ".join(scene_words)

    # Step 1: transcribe with Groq Whisper, biased toward the scene vocabulary
    async with httpx.AsyncClient(timeout=30) as client:
        asr_data = {"model": GROQ_WHISPER_MODEL, "language": "zh", "response_format": "text"}
        if vocab_hint:
            asr_data["prompt"] = vocab_hint
        asr_resp = await client.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            files={"file": ("audio.wav", audio_bytes, "audio/wav")},
            data=asr_data,
        )
        if asr_resp.status_code != 200:
            raise RuntimeError(f"Groq ASR error: {asr_resp.text}")
        from opencc import OpenCC
        transcription = OpenCC("s2twp").convert(asr_resp.text.strip())

    # Step 2: send transcription + vocabulary to Groq LLaMA for feedback
    feedback_prompt = _feedback_prompt(
        transcription, scene_prompt, scene_vocabulary, praat_tone_accuracy, praat_fluency_score, praat_vowel_quality,
        scene_phrases=scene_phrases, scene_suggested_answer=scene_suggested_answer,
        scene_attempt_number=scene_attempt_number,
    )
    payload = {
        "model": GROQ_FEEDBACK_MODEL,
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an expert Mandarin (Traditional Chinese) speaking coach. "
                    "Respond only with valid JSON."
                ),
            },
            {"role": "user", "content": feedback_prompt},
        ],
    }

    async with httpx.AsyncClient(timeout=20) as client:
        llm_resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json=payload,
        )
        if llm_resp.status_code != 200:
            raise RuntimeError(f"Groq LLM error: {llm_resp.text}")

    data = json.loads(llm_resp.json()["choices"][0]["message"]["content"])
    data["provider"] = "groq-audio"
    feedback = _normalize_feedback(data, scene_attempt_number=scene_attempt_number, scene_suggested_answer=scene_suggested_answer)
    if image_b64:
        feedback["content_accuracy"] = _content_accuracy_placeholder(image_b64)
    return {"transcription": transcription, "feedback": feedback}


async def _feedback_with_gemini(
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
    parts: list = [
        {
            "text": _feedback_prompt(
                transcription, scene_prompt, scene_vocabulary,
                praat_tone_accuracy, praat_fluency_score, praat_vowel_quality,
                has_image=bool(image_b64),
                scene_phrases=scene_phrases, scene_suggested_answer=scene_suggested_answer,
                scene_attempt_number=scene_attempt_number,
            )
        }
    ]
    if image_b64:
        parts.append({"inline_data": {"mime_type": image_mime or "image/png", "data": image_b64}})

    payload = {
        "system_instruction": {
            "parts": [
                {
                    "text": (
                        "You are an expert Mandarin (Traditional Chinese) speaking coach for Taiwanese learners. "
                        "Evaluate student speech honestly but encouragingly. "
                        "Always respond in valid JSON only — no markdown fences, no prose outside the JSON."
                    )
                }
            ]
        },
        "contents": [{"parts": parts}],
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

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_FEEDBACK_MODEL}:generateContent?key={GEMINI_API_KEY}",
            json=payload,
        )

    if response.status_code != 200:
        raise RuntimeError(response.text)

    content = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    data = json.loads(_strip_json_fence(content))
    data["provider"] = GEMINI_FEEDBACK_MODEL
    return _normalize_feedback(data, scene_attempt_number=scene_attempt_number, scene_suggested_answer=scene_suggested_answer)


def _feedback_prompt(
    transcription: str,
    scene_prompt: str = "",
    scene_vocabulary: str = "",
    praat_tone_accuracy: float = 0,
    praat_fluency_score: float = 0,
    praat_vowel_quality: str = "",
    has_image: bool = False,
    scene_phrases: str = "",
    scene_suggested_answer: str = "",
    scene_attempt_number: int = 1,
) -> str:
    scene_words = [w.strip() for w in scene_vocabulary.split(",") if w.strip()]
    used = [w for w in scene_words if _word_matches_phonetically(w, transcription)]
    missing = [w for w in scene_words if not _word_matches_phonetically(w, transcription)]

    vocab_context = ""
    if scene_words:
        vocab_context = f"""
Scene vocabulary: {scene_vocabulary}
Words student used (matched by character OR pinyin homophone): {', '.join(used) if used else 'none'}
Words missing: {', '.join(missing) if missing else 'none'}
Note: a word counts as "used" if the student pronounced it correctly even if the ASR wrote a different character with the same sound.
"""

    reference_context = ""
    if scene_phrases.strip() or scene_suggested_answer.strip():
        reference_context = "\nCoaching reference (use to identify specific gaps between what the student said and what is expected):\n"
        if scene_phrases.strip():
            reference_context += f"- Target phrases to use: {scene_phrases.strip()}\n"
        if scene_suggested_answer.strip():
            reference_context += (
                f"- Teacher's model answer: {scene_suggested_answer.strip()}\n"
                "  Compare the student's sentence word-by-word against this model: which vocabulary words are missing, "
                "which grammar slots differ, and what content is not yet described? "
                "Use these gaps to drive your corrective_feedback. Do NOT quote the model answer verbatim in hint "
                "fields on early attempts — instead name the specific missing element (word/pattern/content) so the "
                "student can self-correct.\n"
            )

    praat_context = ""
    if praat_tone_accuracy > 0 or praat_fluency_score > 0:
        praat_context = f"""
Praat acoustic data (use to inform pronunciation feedback):
- Tone accuracy: {round(praat_tone_accuracy)}%
- Fluency score: {round(praat_fluency_score)}%
{f'- Vowel quality: {praat_vowel_quality}' if praat_vowel_quality else ''}
"""

    image_context = (
        "\nAn image is attached above. Judge content_accuracy by checking whether what the "
        "student said actually describes what's in the image — people, objects, setting, "
        "actions, not just whether the target words were said.\n"
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
You are a Mandarin speaking tutor giving structured corrective feedback. This is attempt #{scene_attempt_number} on this picture.
Use the teacher's model answer (if provided above) as the coaching target:
1. Compare the student's sentence against the teacher's model answer word-by-word — identify specific gaps: missing vocabulary, different grammar structure, content not yet described.
2. {"Do NOT reveal the teacher's answer verbatim. Give a targeted hint naming the single most important gap (missing word, wrong grammar slot, or missing scene detail) and ask the student to self-correct. Set reveal_answer to false and leave correct_version empty." if not reveal_now else "This is attempt 3 or later — the student has had two chances with hints. Now reveal the answer: set reveal_answer to true, fill correct_version with the teacher's model answer (or a fluent equivalent). In the hint field, briefly explain the 1-2 key differences between what the student said and the correct version so they understand what changed."}
"""

    return f"""Analyze this Mandarin learner's spoken response and return JSON feedback.

Scene / task: {scene_prompt or "(open topic)"}
Student said: {transcription}
{vocab_context}{reference_context}{praat_context}{image_context}
IMPORTANT — evaluation order:
1. First judge MEANING: does the student's sentence make sense for this picture/scene, using the target vocabulary, grammar pattern, and model answer above as your standard? This is what content_accuracy and coherence capture.
2. Only treat pronunciation as worth detailed feedback if the meaning is acceptable (content_accuracy.accepted is true, or there's no image to judge against). Still score pronunciation_note from the Praat data either way — the app will decide whether to show it to the student.
{corrective_instructions}
Scoring guide:
- vocabulary_coverage.score: 0 = no target words used, 100 = all used correctly
- coherence.score: 0 = incomprehensible, 60 = grammatically acceptable, 90+ = natural native-level
- pronunciation_note.score: base it on Praat tone accuracy % above if provided; 0 = no speech, 50 = many tone errors, 80+ = clear tones
{_FEEDBACK_STYLE_RULES}
Return ONLY this JSON (no markdown, no extra keys):
{{
  "provider": "ai",
  "vocabulary_coverage": {{
    "score": <int 0-100>,
    "used": [<target words the student said>],
    "missing": [<target words not said>],
    "feedback": "<one sentence — name specific words used and missed>"
  }},
  "coherence": {{
    "score": <int 0-100>,
    "feedback": "<one sentence — is the sentence grammatically complete and natural Traditional Chinese?>",
    "corrections": ["<short correction phrase if needed, max 2>"]
  }},
  "pronunciation_note": {{
    "score": <int 0-100>,
    "feedback": "<one sentence — cite specific tones or sounds to improve, based on Praat data>"
  }}{content_accuracy_block},
  "corrective_feedback": {{
    "errors": [<short phrases marking the specific gap vs the teacher's model — e.g. "missing action verb", "wrong word order in the middle clause" — never state the fix itself>],
    "hint": "{'<briefly explain 1-2 key differences between the student answer and the correct version, then show the correct version>' if reveal_now else '<name the single most important missing element compared to what the teacher expects — e.g. which vocabulary word, grammar slot, or image detail is absent — do NOT give the full answer>'}",
    "reveal_answer": {str(reveal_now).lower()},
    "correct_version": "{'<teacher model answer or fluent equivalent>' if reveal_now else ''}"
  }},
  "improved_version": "<a fluent Traditional Chinese sentence that fits the scene and includes the target vocabulary>",
  "practice_prompt": "<one concrete next step the student should try — a hint about which vocabulary/grammar to use or which tone to fix, not the finished sentence>"
}}"""


def _strip_json_fence(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```json"):
        return stripped.removeprefix("```json").removesuffix("```").strip()
    if stripped.startswith("```"):
        return stripped.removeprefix("```").removesuffix("```").strip()
    return stripped


def _normalize_feedback(
    data: Dict,
    scene_attempt_number: int = 1,
    scene_suggested_answer: str = "",
) -> Dict:
    fallback = fallback_language_feedback("")

    vc_raw = data.get("vocabulary_coverage", {})
    coh_raw = data.get("coherence", {})
    pron_raw = data.get("pronunciation_note", {})
    ca_raw = data.get("content_accuracy")
    cf_raw = data.get("corrective_feedback") or {}

    normalized = {
        "provider": data.get("provider", "ai"),
        "vocabulary_coverage": {
            "score": _score(vc_raw.get("score", fallback["vocabulary_coverage"]["score"])),
            "used": [str(w) for w in (vc_raw.get("used") or [])],
            "missing": [str(w) for w in (vc_raw.get("missing") or [])],
            "feedback": str(vc_raw.get("feedback", fallback["vocabulary_coverage"]["feedback"])),
        },
        "coherence": {
            "score": _score(coh_raw.get("score", fallback["coherence"]["score"])),
            "feedback": str(coh_raw.get("feedback", fallback["coherence"]["feedback"])),
            "corrections": [str(c) for c in (coh_raw.get("corrections") or [])[:3]],
        },
        "pronunciation_note": {
            "score": _score(pron_raw.get("score", fallback["pronunciation_note"]["score"])),
            "feedback": str(pron_raw.get("feedback", fallback["pronunciation_note"]["feedback"])),
        },
        "improved_version": str(data.get("improved_version", "")),
        "practice_prompt": str(data.get("practice_prompt", fallback["practice_prompt"])),
    }

    # Server-side source of truth for the reveal gate — never trust the LLM's
    # word for it, since indirect corrective feedback only works if this holds.
    reveal_answer = scene_attempt_number > MAX_HINT_ATTEMPTS
    correct_version = ""
    if reveal_answer:
        correct_version = str(cf_raw.get("correct_version") or "").strip() or scene_suggested_answer.strip()
    normalized["corrective_feedback"] = {
        "errors": [str(e) for e in (cf_raw.get("errors") or [])[:5]],
        "hint": "" if reveal_answer else str(cf_raw.get("hint", "")),
        "reveal_answer": reveal_answer,
        "correct_version": correct_version,
    }

    if isinstance(ca_raw, dict):
        # Only present in ca_raw when the prompt actually asked a vision-capable
        # model to judge it (has_image=True), so this is always a real score.
        ca_score = _score(ca_raw.get("score", 0))
        normalized["content_accuracy"] = {
            "score": ca_score,
            "feedback": str(ca_raw.get("feedback", "")),
            "matched_details": [str(d) for d in (ca_raw.get("matched_details") or [])[:6]],
            "missed_details": [str(d) for d in (ca_raw.get("missed_details") or [])[:6]],
            # Server-side threshold is the source of truth.  In particular,
            # bool("false") is True in Python, so trusting the model's JSON
            # value could accept a low-scoring answer.
            "accepted": ca_score >= CONTENT_ACCURACY_ACCEPT_THRESHOLD,
            "judged": True,
        }
    return normalized


def _normalize_score_block(data: Dict, fallback: Dict) -> Dict:
    return {
        "score": _score(data.get("score", fallback["score"])),
        "feedback": str(data.get("feedback", fallback["feedback"])),
    }


def _normalize_list_block(data: Dict, fallback: Dict, list_key: str) -> Dict:
    items = data.get(list_key, fallback[list_key])
    if not isinstance(items, list):
        items = fallback[list_key]

    return {
        "score": _score(data.get("score", fallback["score"])),
        "feedback": str(data.get("feedback", fallback["feedback"])),
        list_key: [str(item) for item in items[:4]],
    }


def _score(value) -> int:
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return 0


# ── Story-level holistic feedback ──────────────────────────────────────────
#
# Runs once, after a student submits a whole story (all scenes concatenated),
# on top of — never instead of — the per-scene feedback above. A separate
# prompt/pipeline from _feedback_prompt, but unlike the first version of this
# feature, Fluency-and-Coherence and Pronunciation ARE allowed to use the same
# per-scene Praat metrics (tone accuracy, fluency score, word-prosody/
# pronunciation accuracy) already computed during recording — averaged across
# the whole story — since that's real acoustic signal, not a guess. Lexical
# Resource and Grammatical Range and Accuracy stay text-only (Praat has no
# opinion on vocabulary or grammar).

_STORY_FEEDBACK_SYSTEM_PROMPT = (
    "You are an expert Mandarin (Traditional Chinese) speaking coach for Taiwanese learners, "
    "evaluating a full story narration as one connected performance. "
    "Always respond in valid JSON only — no markdown fences, no prose outside the JSON."
)


def _story_feedback_prompt(
    combined_transcript: str,
    avg_tone_accuracy: float = 0,
    avg_fluency_score: float = 0,
    avg_pron_score: float = 0,
    total_pause_count: float = 0,
    longest_single_pause: float = 0,
    total_utterance_count: float = 0,
    scene_count: int = 1,
    total_choppy_pause_count: float = 0,
    avg_articulation_rate: float = 0,
) -> str:
    scene_count = max(1, scene_count, combined_transcript.count("[Scene "))
    praat_context = ""
    if avg_tone_accuracy > 0 or avg_fluency_score > 0 or avg_pron_score > 0:
        praat_context = f"""
Praat acoustic data, averaged across every scene in this story (this is real measured data — use it to ground tone, word_stress, and rhythm_pace, and feel free to cite these numbers directly in your feedback):
- Average tone accuracy: {round(avg_tone_accuracy)}%
- Average fluency score: {round(avg_fluency_score)}%
- Average pronunciation/prosody accuracy: {round(avg_pron_score)}%
"""
    delivery_context = ""
    if total_pause_count > 0 or total_utterance_count > 0 or longest_single_pause > 0:
        avg_pauses_per_scene = round(total_pause_count / max(1, scene_count), 1)
        delivery_context = f"""
Delivery data, measured directly from the audio across the whole story (real counts, not an estimate — cite these directly in pausing's and rhythm_pace's feedback):
- Total pauses across the story: {round(total_pause_count)} ({avg_pauses_per_scene} per scene on average)
- Longest single pause anywhere in the story: {longest_single_pause:.1f}s
- Total utterances (speech chunks between pauses): {round(total_utterance_count)}
- Pauses that broke up a phrase rather than landing at a natural boundary (comma/connective): {round(total_choppy_pause_count)}
- Average articulation rate (syllables/sec while actually speaking, pauses excluded): {avg_articulation_rate:.1f}
"""

    return f"""You are evaluating a STORY-LEVEL transcript: everything a student said across every scene of a picture story, concatenated in order as one connected narration — not a single sentence. The student was reading an assigned script for each scene, not composing freely, so vocabulary and grammar choice aren't being tested here — only delivery.

This story has exactly {scene_count} scene(s), listed below in order as [Scene 1], [Scene 2], etc. Base every dimension on ALL {scene_count} scene(s) together, not just the first or the longest one. A scene marked "(no speech transcribed for this scene)" means the student attempted that scene but nothing was recognized — treat that as a real gap (it should weigh down every dimension), not as a scene to ignore.

Student's full story transcript (scene by scene):
{combined_transcript}
{praat_context}{delivery_context}
Score these four pronunciation-focused dimensions, all grounded in the real measured Praat/delivery data above wherever it's provided. The student will NOT see the numeric score — only your feedback text — so every "feedback" field must be actionable coaching, not just a description: briefly name the current level in one clause, then spend most of the sentence(s) on 1-2 concrete, specific things the student should do differently NEXT time to improve this particular skill. Cite the actual numbers directly (e.g. "tone accuracy averaged 72%", "you paused 6 times, including one 1.8s gap") rather than vague praise or criticism.

1. tone — base this on the average tone accuracy above (cite it directly). Point at tones as the likely weak spot and suggest re-practicing the specific characters flagged low-accuracy in the per-scene feedback.
2. word_stress — base this on the average pronunciation/prosody accuracy above (cite it directly). This measures whether content words (nouns, verbs, adjectives) are stressed — louder/higher-pitched — relative to function words (的/了/嗎). Suggest listening for that contrast.
3. rhythm_pace — base this on the average fluency score and articulation rate above (cite the syllables/sec figure directly). Judge whether the pace was too slow, too fast, or good, and suggest a concrete pacing adjustment.
4. pausing — base this on the pause count, longest pause, and choppy-vs-natural pause breakdown above (cite the actual counts directly). Judge whether pauses landed at natural clause/phrase boundaries or broke up phrases, and suggest a concrete way to reduce disruptive pausing.

Return ONLY this JSON (no markdown):
{{
  "provider": "ai",
  "tone": {{"score": <int 0-100, internal only, not shown to the student>, "feedback": "<2-3 sentences: brief current-level note + concrete, specific suggestion for how to improve>"}},
  "word_stress": {{"score": <int 0-100, internal only, not shown to the student>, "feedback": "<2-3 sentences: brief current-level note + concrete, specific suggestion for how to improve>"}},
  "rhythm_pace": {{"score": <int 0-100, internal only, not shown to the student>, "feedback": "<2-3 sentences: brief current-level note + concrete, specific suggestion for how to improve>"}},
  "pausing": {{"score": <int 0-100, internal only, not shown to the student>, "feedback": "<2-3 sentences: brief current-level note + concrete, specific suggestion for how to improve>"}}
}}"""


def _tone_dimension(avg_tone_accuracy: float) -> Dict:
    if avg_tone_accuracy <= 0:
        return {
            "score": 0,
            "feedback": "No tone data was available for this story — make sure each scene finishes analysis before submitting.",
            "judged": False,
        }
    return {
        "score": max(0, min(100, round(avg_tone_accuracy))),
        "feedback": (
            f"Tone-contour accuracy averaged {round(avg_tone_accuracy)}% across the story. "
            "Go back through the per-scene pitch charts and re-practice the specific characters "
            "flagged as low-accuracy — repeating just those a few times out loud helps more than "
            "re-recording the whole story."
        ),
        "judged": True,
    }


def _word_stress_dimension(avg_pron_score: float) -> Dict:
    if avg_pron_score <= 0:
        return {
            "score": 0,
            "feedback": "No word-stress data was available for this story.",
            "judged": False,
        }
    return {
        "score": max(0, min(100, round(avg_pron_score))),
        "feedback": (
            f"Word-stress and prosody accuracy averaged {round(avg_pron_score)}% across the story. "
            "Content words (nouns, verbs, adjectives) should sound a little louder and higher-pitched "
            "than function words like 的/了/嗎 — listen for that contrast in your recordings."
        ),
        "judged": True,
    }
