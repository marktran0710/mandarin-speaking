import json
import os
from typing import Dict, List

import httpx
from dotenv import load_dotenv

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
OPENAI_FEEDBACK_MODEL = os.getenv("OPENAI_FEEDBACK_MODEL", "gpt-4o-mini")
GEMINI_FEEDBACK_MODEL = os.getenv("GEMINI_FEEDBACK_MODEL", "gemini-2.0-flash")
AI_FEEDBACK_PROVIDER = os.getenv("AI_FEEDBACK_PROVIDER", "local").lower()


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
    used_words = [w for w in scene_words if w in text]
    missing_words = [w for w in scene_words if w not in text]

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
) -> Dict:
    text = transcription.strip()
    if not text:
        return fallback_language_feedback(text, scene_prompt, scene_vocabulary, praat_tone_accuracy, praat_fluency_score, praat_vowel_quality)

    if AI_FEEDBACK_PROVIDER == "local":
        return fallback_language_feedback(text, scene_prompt, scene_vocabulary, praat_tone_accuracy, praat_fluency_score, praat_vowel_quality)

    if AI_FEEDBACK_PROVIDER == "openai" and OPENAI_API_KEY:
        try:
            return await _feedback_with_openai(text, scene_prompt, scene_vocabulary, praat_tone_accuracy, praat_fluency_score, praat_vowel_quality)
        except Exception as exc:
            print(f"OpenAI feedback failed, using local fallback: {exc}")

    if GEMINI_API_KEY:
        try:
            return await _feedback_with_gemini(text, scene_prompt, scene_vocabulary, praat_tone_accuracy, praat_fluency_score, praat_vowel_quality)
        except Exception as exc:
            print(f"Gemini feedback failed, using local fallback: {exc}")

    if OPENAI_API_KEY:
        try:
            return await _feedback_with_openai(text, scene_prompt, scene_vocabulary, praat_tone_accuracy, praat_fluency_score, praat_vowel_quality)
        except Exception as exc:
            print(f"OpenAI feedback failed, using local fallback: {exc}")

    return fallback_language_feedback(text, scene_prompt, scene_vocabulary, praat_tone_accuracy, praat_fluency_score, praat_vowel_quality)


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


async def _feedback_with_gemini(
    transcription: str,
    scene_prompt: str = "",
    scene_vocabulary: str = "",
    praat_tone_accuracy: float = 0,
    praat_fluency_score: float = 0,
    praat_vowel_quality: str = "",
) -> Dict:
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            "Return only valid JSON. "
                            f"{_feedback_prompt(transcription, scene_prompt, scene_vocabulary, praat_tone_accuracy, praat_fluency_score, praat_vowel_quality)}"
                        )
                    }
                ]
            }
        ]
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
    used = [w for w in scene_words if w in transcription]
    missing = [w for w in scene_words if w not in transcription]

    vocab_context = ""
    if scene_words:
        vocab_context = f"""
Scene vocabulary: {scene_vocabulary}
Words student used: {', '.join(used) if used else 'none'}
Words missing: {', '.join(missing) if missing else 'none'}
"""

    praat_context = ""
    if praat_tone_accuracy > 0 or praat_fluency_score > 0:
        praat_context = f"""
Praat acoustic data (use to inform pronunciation feedback):
- Tone accuracy: {round(praat_tone_accuracy)}%
- Fluency score: {round(praat_fluency_score)}%
{f'- Vowel quality: {praat_vowel_quality}' if praat_vowel_quality else ''}
"""

    return f"""
You are a Mandarin speaking coach. Analyze this student's transcription:

Student said: {transcription}
Scene prompt: {scene_prompt or "(none)"}
{vocab_context}{praat_context}
Return JSON shaped EXACTLY like this (no extra keys):
{{
  "provider": "ai",
  "vocabulary_coverage": {{
    "score": 0-100,
    "used": ["word1", "word2"],
    "missing": ["word3"],
    "feedback": "one sentence: which scene words were used and which were missed"
  }},
  "coherence": {{
    "score": 0-100,
    "feedback": "one sentence on whether the sentence is natural and grammatically complete",
    "corrections": ["specific short correction if needed"]
  }},
  "pronunciation_note": {{
    "score": 0-100,
    "feedback": "one sentence using the Praat data — name specific tones or sounds to improve"
  }},
  "improved_version": "a natural Mandarin sentence that fits the scene and uses the target vocabulary",
  "practice_prompt": "one actionable next step for the student"
}}
"""


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
