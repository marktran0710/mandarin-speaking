import json
import os
from typing import Dict, List

import httpx
from dotenv import load_dotenv
from pypinyin import lazy_pinyin, Style

import caf_metrics


load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env.local"))


def clean_api_key(value: str | None) -> str | None:
    key = (value or "").strip()
    if not key or "your_" in key.lower() or key.lower().endswith("_here"):
        return None
    return key


OPENAI_API_KEY = clean_api_key(os.getenv("OPENAI_API_KEY") or os.getenv("VITE_OPENAI_API_KEY"))
GEMINI_API_KEY = clean_api_key(os.getenv("GEMINI_API_KEY") or os.getenv("VITE_GEMINI_API_KEY"))
GROQ_API_KEY = clean_api_key(os.getenv("GROQ_API_KEY") or os.getenv("VITE_GROQ_API_KEY"))
OPENAI_FEEDBACK_MODEL = os.getenv("OPENAI_FEEDBACK_MODEL", "gpt-4o-mini")
GEMINI_FEEDBACK_MODEL = os.getenv("GEMINI_FEEDBACK_MODEL", "gemini-2.0-flash")
GROQ_FEEDBACK_MODEL = os.getenv("GROQ_FEEDBACK_MODEL", "llama-3.3-70b-versatile")
AI_FEEDBACK_PROVIDER = os.getenv("AI_FEEDBACK_PROVIDER", "local").lower()


def available_providers() -> List[Dict]:
    """Provider options for the student-facing engine picker.

    ``available`` is False when the provider needs an API key that isn't
    configured; the UI shows it disabled so the choice stays honest.
    """
    return [
        {"id": "local", "label": "Local (offline CAF)", "available": True},
        {"id": "groq", "label": "Groq (free)", "available": bool(GROQ_API_KEY)},
        {"id": "gemini", "label": "Gemini", "available": bool(GEMINI_API_KEY)},
        {"id": "openai", "label": "ChatGPT (OpenAI)", "available": bool(OPENAI_API_KEY)},
    ]


def default_provider() -> str:
    return AI_FEEDBACK_PROVIDER


def _to_pinyin(text: str) -> str:
    """Convert Chinese text to tone-marked pinyin string for phonetic comparison."""
    return " ".join(lazy_pinyin(text, style=Style.TONE3))


def _word_matches_phonetically(vocab_word: str, transcription: str) -> bool:
    """Return True if vocab_word appears in transcription — by character OR by pinyin.

    This handles ASR homophones: the student said the right sound but the
    speech-to-text wrote a different character with the same pronunciation.
    """
    if vocab_word in transcription:
        return True
    # Pinyin of the full vocab word vs a sliding window in the transcription
    word_pinyin = _to_pinyin(vocab_word)
    # Build pinyin of every same-length substring in the transcription
    n = len(vocab_word)
    for i in range(len(transcription) - n + 1):
        segment = transcription[i : i + n]
        if _to_pinyin(segment) == word_pinyin:
            return True
    return False


def fallback_language_feedback(
    transcription: str,
    scene_prompt: str = "",
    scene_vocabulary: str = "",
    praat_tone_accuracy: float = 0,
    praat_fluency_score: float = 0,
    praat_vowel_quality: str = "",
    praat_pause_analysis: Dict | None = None,
    praat_speech_rate: float = 0,
) -> Dict:
    """Offline language feedback grounded in the CAF framework.

    Vocabulary blends task coverage with lexical diversity (Guiraud/MTLD),
    coherence uses syntactic complexity (length + subordination), and the
    pronunciation note reports the tone-contour proxy for Goodness of
    Pronunciation. See ``caf_metrics`` for the measures and citations.
    """
    text = transcription.strip()
    character_count = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")

    if not text:
        prompt_hint = f" about: {scene_prompt}" if scene_prompt else ""
        return {
            "provider": "local",
            "vocabulary_coverage": {
                "score": 0,
                "used": [],
                "missing": [],
                "feedback": f"No transcription yet. Try one short sentence{prompt_hint}.",
            },
            "coherence": {
                "score": 0,
                "feedback": "Record a sentence to get coherence feedback.",
                "corrections": [],
            },
            "pronunciation_note": {
                "score": 0,
                "feedback": f"Record a sentence to get pronunciation feedback.",
            },
            "improved_version": "",
            "practice_prompt": f"Record one simple Mandarin sentence{prompt_hint}.",
        }

    tokens = caf_metrics.segment_words(text)
    lexical = caf_metrics.lexical_metrics(tokens)
    complexity = caf_metrics.syntactic_complexity(tokens, text)

    # ── Vocabulary: task coverage blended with lexical diversity ────────────
    scene_words = [w.strip() for w in scene_vocabulary.split(",") if w.strip()]
    used_words = [w for w in scene_words if _word_matches_phonetically(w, text)]
    missing_words = [w for w in scene_words if not _word_matches_phonetically(w, text)]

    if not scene_words:
        vocab_score = lexical["score"]
        vocab_feedback = (
            f"Lexical diversity: Guiraud index {lexical['guiraud']} "
            f"({lexical['types']} unique of {lexical['tokens']} words)."
        )
    else:
        coverage_pct = round(len(used_words) / len(scene_words) * 100)
        # 60% task coverage + 40% lexical diversity (CAF lexical sub-construct).
        vocab_score = int(round(0.6 * coverage_pct + 0.4 * lexical["score"]))
        if not used_words:
            vocab_feedback = f"None of the scene words were used. Try saying: {', '.join(scene_words[:3])}."
        elif not missing_words:
            vocab_feedback = (
                f"All scene words used: {', '.join(used_words)}. "
                f"Lexical diversity (Guiraud) {lexical['guiraud']}."
            )
        else:
            vocab_feedback = (
                f"Used {len(used_words)}/{len(scene_words)}: {', '.join(used_words)}. "
                f"Still missing: {', '.join(missing_words[:3])}. Guiraud {lexical['guiraud']}."
            )

    # \u2500\u2500 Coherence: syntactic complexity (length + subordination) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    coherence_score = complexity["score"]
    coherence_corrections: list = []
    if complexity["length"] < 4:
        coherence_feedback = (
            f"Very short \u2014 only {complexity['length']} words. "
            "Aim for subject + verb + object."
        )
        coherence_corrections = ["Add a subject (\u8ab0)", "Add a verb (\u505a\u4ec0\u9ebc)"]
    elif not complexity["connectives"]:
        coherence_feedback = (
            f"{complexity['length']} words but no connectives. "
            "Link ideas with words like \u56e0\u70ba / \u6240\u4ee5 / \u7136\u5f8c."
        )
        coherence_corrections = ["Join two clauses with \u7136\u5f8c or \u56e0\u70ba"]
    else:
        coherence_feedback = (
            f"{complexity['length']} words with connectives "
            f"{', '.join(complexity['connectives'][:3])} \u2014 good clause linking."
        )

    # \u2500\u2500 Pronunciation: tone-contour proxy for Goodness of Pronunciation \u2500\u2500\u2500\u2500\u2500
    tone_pct = round(praat_tone_accuracy)
    fluency_pct = round(praat_fluency_score)
    if tone_pct >= 80 and fluency_pct >= 75:
        pron_score = 88
        pron_feedback = f"Tones and rhythm both sound strong ({tone_pct}% tone-contour match)."
    elif tone_pct >= 60:
        pron_score = 65
        pron_feedback = f"Tone-contour match {tone_pct}% \u2014 keep working on the weaker tones. Rhythm: {fluency_pct}%."
    elif tone_pct > 0:
        pron_score = 45
        pron_feedback = f"Tone-contour match {tone_pct}% \u2014 focus on the tones marked in the pitch chart."
    else:
        pron_score = 50
        pron_feedback = "Speak clearly and hold each syllable long enough for tone recognition."

    if praat_pause_analysis is not None:
        fluency = caf_metrics.fluency_metrics(
            praat_speech_rate, praat_pause_analysis, character_count
        )
        pron_feedback += (
            f" Fluency: {fluency['articulation_rate']} syl/s articulation, "
            f"mean run {fluency['mean_length_of_run']} syllables."
        )
    if praat_vowel_quality:
        pron_feedback += f" Vowel quality: {praat_vowel_quality}."

    practice_next = (
        f"Say the sentence again adding {missing_words[0]}."
        if missing_words else
        "Add a connective (\u7136\u5f8c / \u56e0\u70ba) to extend the sentence."
    )

    return {
        "provider": "local",
        "vocabulary_coverage": {
            "score": vocab_score,
            "used": used_words,
            "missing": missing_words,
            "feedback": vocab_feedback,
        },
        "coherence": {
            "score": coherence_score,
            "feedback": coherence_feedback,
            "corrections": coherence_corrections,
        },
        "pronunciation_note": {
            "score": pron_score,
            "feedback": pron_feedback,
        },
        "improved_version": text,
        "practice_prompt": practice_next,
    }


async def generate_language_feedback(
    transcription: str,
    scene_prompt: str = "",
    scene_vocabulary: str = "",
    praat_tone_accuracy: float = 0,
    praat_fluency_score: float = 0,
    praat_vowel_quality: str = "",
    provider: str | None = None,
) -> Dict:
    """Produce language feedback.

    ``provider`` overrides the env default per request ("local" | "gemini" |
    "openai"). The requested engine is tried first; if it lacks a key or the
    network call fails, we degrade gracefully to any other configured cloud
    provider and finally to the offline CAF engine, so the student always
    gets feedback.
    """
    text = transcription.strip()
    args = (text, scene_prompt, scene_vocabulary, praat_tone_accuracy, praat_fluency_score, praat_vowel_quality)
    if not text:
        return fallback_language_feedback(*args)

    chosen = (provider or AI_FEEDBACK_PROVIDER or "local").strip().lower()
    if chosen == "local":
        return fallback_language_feedback(*args)

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
            return await callers[name](*args)
        except Exception as exc:
            print(f"{name} feedback failed, trying next engine: {exc}")

    return fallback_language_feedback(*args)


async def _feedback_with_groq(
    transcription: str,
    scene_prompt: str = "",
    scene_vocabulary: str = "",
    praat_tone_accuracy: float = 0,
    praat_fluency_score: float = 0,
    praat_vowel_quality: str = "",
) -> Dict:
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
                "content": _feedback_prompt(transcription, scene_prompt, scene_vocabulary, praat_tone_accuracy, praat_fluency_score, praat_vowel_quality),
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
    return _normalize_feedback(data)


async def _feedback_with_openai(
    transcription: str,
    scene_prompt: str = "",
    scene_vocabulary: str = "",
    praat_tone_accuracy: float = 0,
    praat_fluency_score: float = 0,
    praat_vowel_quality: str = "",
) -> Dict:
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
                "content": _feedback_prompt(transcription, scene_prompt, scene_vocabulary, praat_tone_accuracy, praat_fluency_score, praat_vowel_quality),
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
    return _normalize_feedback(data)


def _audio_assessment_prompt(
    scene_prompt: str,
    vocab_line: str,
    praat_context: str,
    provider_tag: str,
) -> str:
    return f"""Listen to this Mandarin audio recording and do two things:
1. Transcribe it exactly in Traditional Chinese (繁體中文).
2. Evaluate the student's speech using the context below.

Scene / task: {scene_prompt or "(open topic)"}
{vocab_line}{praat_context}

Scoring guide:
- vocabulary_coverage.score: 0 = no target words used, 100 = all used
- coherence.score: 60 = acceptable grammar, 90+ = natural native-level
- pronunciation_note.score: use Praat tone accuracy if provided; 80+ = clear tones

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
  }},
  "improved_version": "<a fluent Traditional Chinese sentence fitting the scene with the target vocabulary>",
  "practice_prompt": "<one concrete next step for the student>"
}}"""


def _build_audio_context(
    scene_prompt: str,
    scene_vocabulary: str,
    praat_tone_accuracy: float,
    praat_fluency_score: float,
    praat_vowel_quality: str,
) -> tuple[str, str]:
    """Return (vocab_line, praat_context) strings for audio assessment prompts."""
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
    return vocab_line, praat_context


def _unpack_audio_result(data: dict, provider_tag: str) -> dict:
    transcription = data.pop("transcription", "")
    data["provider"] = provider_tag
    return {"transcription": transcription, "feedback": _normalize_feedback(data)}


async def assess_audio_with_gemini(
    audio_bytes: bytes,
    scene_prompt: str = "",
    scene_vocabulary: str = "",
    praat_tone_accuracy: float = 0,
    praat_fluency_score: float = 0,
    praat_vowel_quality: str = "",
) -> Dict:
    """Multimodal Gemini call: audio + vocabulary → transcription + feedback in one shot."""
    import base64
    audio_b64 = base64.b64encode(audio_bytes).decode()
    vocab_line, praat_context = _build_audio_context(
        scene_prompt, scene_vocabulary, praat_tone_accuracy, praat_fluency_score, praat_vowel_quality
    )
    prompt = _audio_assessment_prompt(scene_prompt, vocab_line, praat_context, "gemini-audio")

    payload = {
        "system_instruction": {
            "parts": [{"text": (
                "You are an expert Mandarin (Traditional Chinese) speaking coach. "
                "Listen carefully to the audio. Respond only with valid JSON."
            )}]
        },
        "contents": [{"parts": [
            {"inline_data": {"mime_type": "audio/wav", "data": audio_b64}},
            {"text": prompt},
        ]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
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
    return _unpack_audio_result(json.loads(_strip_json_fence(raw)), "gemini-audio")


async def assess_audio_with_openai(
    audio_bytes: bytes,
    scene_prompt: str = "",
    scene_vocabulary: str = "",
    praat_tone_accuracy: float = 0,
    praat_fluency_score: float = 0,
    praat_vowel_quality: str = "",
) -> Dict:
    """Multimodal GPT-4o call: audio + vocabulary → transcription + feedback in one shot."""
    import base64
    audio_b64 = base64.b64encode(audio_bytes).decode()
    vocab_line, praat_context = _build_audio_context(
        scene_prompt, scene_vocabulary, praat_tone_accuracy, praat_fluency_score, praat_vowel_quality
    )
    prompt = _audio_assessment_prompt(scene_prompt, vocab_line, praat_context, "openai-audio")

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
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {"data": audio_b64, "format": "wav"},
                    },
                    {"type": "text", "text": prompt},
                ],
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
    return _unpack_audio_result(json.loads(content), "openai-audio")


async def assess_audio_with_groq(
    audio_bytes: bytes,
    scene_prompt: str = "",
    scene_vocabulary: str = "",
    praat_tone_accuracy: float = 0,
    praat_fluency_score: float = 0,
    praat_vowel_quality: str = "",
) -> Dict:
    """Groq two-step pipeline: Whisper ASR + LLaMA feedback in one function.

    Groq's LLM API doesn't accept audio input yet, so we chain:
    audio → Groq whisper-large-v3 (transcription) → Groq LLaMA (feedback)
    Both calls share the same vocabulary context.
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
    vocab_line, praat_context = _build_audio_context(
        scene_prompt, scene_vocabulary, praat_tone_accuracy, praat_fluency_score, praat_vowel_quality
    )
    feedback_prompt = _feedback_prompt(
        transcription, scene_prompt, scene_vocabulary, praat_tone_accuracy, praat_fluency_score, praat_vowel_quality
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
    feedback = _normalize_feedback(data)
    return {"transcription": transcription, "feedback": feedback}


async def _feedback_with_gemini(
    transcription: str,
    scene_prompt: str = "",
    scene_vocabulary: str = "",
    praat_tone_accuracy: float = 0,
    praat_fluency_score: float = 0,
    praat_vowel_quality: str = "",
) -> Dict:
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
        "contents": [
            {
                "parts": [
                    {
                        "text": _feedback_prompt(
                            transcription, scene_prompt, scene_vocabulary,
                            praat_tone_accuracy, praat_fluency_score, praat_vowel_quality
                        )
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
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
    return _normalize_feedback(data)


def _feedback_prompt(
    transcription: str,
    scene_prompt: str = "",
    scene_vocabulary: str = "",
    praat_tone_accuracy: float = 0,
    praat_fluency_score: float = 0,
    praat_vowel_quality: str = "",
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

    praat_context = ""
    if praat_tone_accuracy > 0 or praat_fluency_score > 0:
        praat_context = f"""
Praat acoustic data (use to inform pronunciation feedback):
- Tone accuracy: {round(praat_tone_accuracy)}%
- Fluency score: {round(praat_fluency_score)}%
{f'- Vowel quality: {praat_vowel_quality}' if praat_vowel_quality else ''}
"""

    return f"""Analyze this Mandarin learner's spoken response and return JSON feedback.

Scene / task: {scene_prompt or "(open topic)"}
Student said: {transcription}
{vocab_context}{praat_context}
Scoring guide:
- vocabulary_coverage.score: 0 = no target words used, 100 = all used correctly
- coherence.score: 0 = incomprehensible, 60 = grammatically acceptable, 90+ = natural native-level
- pronunciation_note.score: base it on Praat tone accuracy % above if provided; 0 = no speech, 50 = many tone errors, 80+ = clear tones

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
  }},
  "improved_version": "<a fluent Traditional Chinese sentence that fits the scene and includes the target vocabulary>",
  "practice_prompt": "<one concrete next step — e.g. 'Say X again and hold the falling tone on Y'>"
}}"""


def _strip_json_fence(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```json"):
        return stripped.removeprefix("```json").removesuffix("```").strip()
    if stripped.startswith("```"):
        return stripped.removeprefix("```").removesuffix("```").strip()
    return stripped


def _normalize_feedback(data: Dict) -> Dict:
    fallback = fallback_language_feedback("")

    vc_raw = data.get("vocabulary_coverage", {})
    coh_raw = data.get("coherence", {})
    pron_raw = data.get("pronunciation_note", {})

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
