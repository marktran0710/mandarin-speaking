import json
import os
from typing import Dict, List

import httpx
from dotenv import load_dotenv
from pypinyin import lazy_pinyin, Style
import taiwan_pinyin; taiwan_pinyin.apply()

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


CONTENT_ACCURACY_ACCEPT_THRESHOLD = 60

# Indirect corrective feedback: hint-only for this many attempts, then reveal
# the correct version on the next one. Matches "after two attempts" — attempts
# 1 and 2 get hints, attempt 3+ gets the answer.
MAX_HINT_ATTEMPTS = 2


def _corrective_feedback_placeholder() -> Dict:
    return {"errors": [], "hint": "", "reveal_answer": False, "correct_version": ""}


def _content_accuracy_placeholder(image_b64: str | None) -> Dict:
    """Offline content-accuracy block — vision comparison needs a vision-capable AI provider.

    No image, no AI provider, or an engine without vision input (Groq) means
    we cannot judge meaning, so we don't block pronunciation feedback on a
    check we're unable to perform. ``judged`` tells the frontend this score
    is a placeholder, not a real (bad) result, so it shouldn't be rendered as
    a score bar.
    """
    if not image_b64:
        return {"score": 0, "feedback": "", "matched_details": [], "missed_details": [], "accepted": True, "judged": False}
    return {
        "score": 0,
        "feedback": "Comparing your description against the image needs a vision-capable AI "
        "provider — switch to Gemini or ChatGPT to get this feedback.",
        "matched_details": [],
        "missed_details": [],
        "accepted": True,
        "judged": False,
    }


def _word_stress_note(word_prosody: List[Dict] | None) -> str:
    """Build a one-line note about word-level stress from word_prosody segments."""
    if not word_prosody:
        return ""
    try:
        from praat_analyzer import word_stress_summary
        summary = word_stress_summary(word_prosody)
    except Exception:
        return ""

    parts: List[str] = []
    de_acc = summary.get("de_accented_words", [])
    if de_acc:
        words = "、".join(de_acc[:3])
        parts.append(f"Content words {words} were under-stressed (pitch below average)")

    slope = summary.get("topline_slope_hz_per_sec", 0.0)
    if slope < -20:
        parts.append("natural pitch declination across the sentence")
    elif slope > 15:
        parts.append("pitch rose across the sentence — try letting it decline naturally")

    return "; ".join(parts) if parts else ""


def fallback_language_feedback(
    transcription: str,
    scene_prompt: str = "",
    scene_vocabulary: str = "",
    praat_tone_accuracy: float = 0,
    praat_fluency_score: float = 0,
    praat_vowel_quality: str = "",
    praat_pause_analysis: Dict | None = None,
    praat_speech_rate: float = 0,
    word_prosody: List[Dict] | None = None,
    image_b64: str | None = None,
    image_mime: str = "",
    scene_grammar_pattern: str = "",
    scene_suggested_answer: str = "",
    scene_attempt_number: int = 1,
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
        all_scene_words = [w.strip() for w in scene_vocabulary.split(",") if w.strip()]
        return {
            "provider": "local",
            "vocabulary_coverage": {
                "score": 0,
                "used": [],
                "missing": all_scene_words,
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
            "content_accuracy": _content_accuracy_placeholder(image_b64),
            "corrective_feedback": _corrective_feedback_placeholder(),
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
        vocab_score = coverage_pct
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
    stress_note = _word_stress_note(word_prosody)
    if stress_note:
        pron_feedback += f" Word stress: {stress_note}."

    practice_next = (
        f"Say the sentence again adding {missing_words[0]}."
        if missing_words else
        "Add a connective (\u7136\u5f8c / \u56e0\u70ba) to extend the sentence."
    )

    # \u2500\u2500 Indirect corrective feedback: hint for the first two attempts, then
    # reveal the teacher's model answer (or our own corrected sentence) \u2500\u2500\u2500\u2500\u2500\u2500
    reveal_answer = scene_attempt_number > MAX_HINT_ATTEMPTS
    local_errors: list = []
    if missing_words:
        local_errors.append(f"Missing vocabulary: {', '.join(missing_words[:3])}")
    if tone_pct and tone_pct < 70:
        local_errors.append("Some tones don't match the expected pitch shape")
    if not complexity["connectives"] and complexity["length"] >= 4:
        local_errors.append("Sentence could use a connective to link ideas")

    if reveal_answer:
        correct_version = scene_suggested_answer.strip() or text
        corrective_hint = "Compare your sentence with the correct version below."
    else:
        correct_version = ""
        if missing_words:
            corrective_hint = f"Try adding the word \u300c{missing_words[0]}\u300d somewhere in your sentence."
        elif scene_grammar_pattern.strip():
            corrective_hint = f"Check your sentence against this pattern: {scene_grammar_pattern.strip()}"
        else:
            corrective_hint = "Listen back to your sentence \u2014 does it fully describe the picture?"

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
        "content_accuracy": _content_accuracy_placeholder(image_b64),
        "corrective_feedback": {
            "errors": local_errors,
            "hint": corrective_hint,
            "reveal_answer": reveal_answer,
            "correct_version": correct_version,
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
    image_b64: str | None = None,
    image_mime: str = "",
    scene_grammar_pattern: str = "",
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
        "scene_grammar_pattern": scene_grammar_pattern,
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
    scene_grammar_pattern: str = "",
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
                    scene_grammar_pattern=scene_grammar_pattern, scene_suggested_answer=scene_suggested_answer,
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
    scene_grammar_pattern: str = "",
    scene_suggested_answer: str = "",
    scene_attempt_number: int = 1,
) -> Dict:
    prompt_text = _feedback_prompt(
        transcription, scene_prompt, scene_vocabulary, praat_tone_accuracy, praat_fluency_score, praat_vowel_quality,
        has_image=bool(image_b64),
        scene_grammar_pattern=scene_grammar_pattern, scene_suggested_answer=scene_suggested_answer,
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
    scene_grammar_pattern: str = "",
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
    if scene_grammar_pattern.strip() or scene_suggested_answer.strip():
        reference_context = "\nCoaching reference (use to identify specific gaps between what the student said and what is expected):\n"
        if scene_grammar_pattern.strip():
            reference_context += f"- Target grammar pattern: {scene_grammar_pattern.strip()}\n"
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
    scene_grammar_pattern: str = "",
    scene_suggested_answer: str = "",
    scene_attempt_number: int = 1,
) -> Dict:
    """Multimodal Gemini call: audio + image + vocabulary → transcription + feedback in one shot."""
    import base64
    audio_b64 = base64.b64encode(audio_bytes).decode()
    vocab_line, praat_context, reference_context = _build_audio_context(
        scene_prompt, scene_vocabulary, praat_tone_accuracy, praat_fluency_score, praat_vowel_quality,
        scene_grammar_pattern, scene_suggested_answer,
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
    scene_grammar_pattern: str = "",
    scene_suggested_answer: str = "",
    scene_attempt_number: int = 1,
) -> Dict:
    """Multimodal GPT-4o call: audio + image + vocabulary → transcription + feedback in one shot."""
    import base64
    audio_b64 = base64.b64encode(audio_bytes).decode()
    vocab_line, praat_context, reference_context = _build_audio_context(
        scene_prompt, scene_vocabulary, praat_tone_accuracy, praat_fluency_score, praat_vowel_quality,
        scene_grammar_pattern, scene_suggested_answer,
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


async def assess_audio_with_groq(
    audio_bytes: bytes,
    scene_prompt: str = "",
    scene_vocabulary: str = "",
    praat_tone_accuracy: float = 0,
    praat_fluency_score: float = 0,
    praat_vowel_quality: str = "",
    image_b64: str | None = None,
    image_mime: str = "",
    scene_grammar_pattern: str = "",
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
        scene_grammar_pattern=scene_grammar_pattern, scene_suggested_answer=scene_suggested_answer,
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
    scene_grammar_pattern: str = "",
    scene_suggested_answer: str = "",
    scene_attempt_number: int = 1,
) -> Dict:
    parts: list = [
        {
            "text": _feedback_prompt(
                transcription, scene_prompt, scene_vocabulary,
                praat_tone_accuracy, praat_fluency_score, praat_vowel_quality,
                has_image=bool(image_b64),
                scene_grammar_pattern=scene_grammar_pattern, scene_suggested_answer=scene_suggested_answer,
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
    scene_grammar_pattern: str = "",
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
    if scene_grammar_pattern.strip() or scene_suggested_answer.strip():
        reference_context = "\nCoaching reference (use to identify specific gaps between what the student said and what is expected):\n"
        if scene_grammar_pattern.strip():
            reference_context += f"- Target grammar pattern: {scene_grammar_pattern.strip()}\n"
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
            "accepted": bool(ca_raw.get("accepted", ca_score >= CONTENT_ACCURACY_ACCEPT_THRESHOLD)),
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
