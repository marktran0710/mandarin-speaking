import json
import os
from typing import Dict, List

import httpx
from dotenv import load_dotenv


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
) -> Dict:
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

    # Vocabulary coverage
    scene_words = [w.strip() for w in scene_vocabulary.split(",") if w.strip()]
    used_words = [w for w in scene_words if w in text]
    missing_words = [w for w in scene_words if w not in text]

    if not scene_words:
        vocab_score = 60
        vocab_feedback = "No scene vocabulary defined. Use specific nouns and verbs that fit the scene."
    elif not missing_words:
        vocab_score = 100
        vocab_feedback = f"All scene words used: {', '.join(used_words)}. Excellent!"
    elif not used_words:
        vocab_score = 20
        vocab_feedback = f"None of the scene words were detected. Try using: {', '.join(scene_words[:3])}."
    else:
        pct = round(len(used_words) / len(scene_words) * 100)
        vocab_score = pct
        vocab_feedback = f"Used {len(used_words)}/{len(scene_words)}: {', '.join(used_words)}. Still missing: {', '.join(missing_words[:3])}."

    # Coherence (structure-based heuristic)
    if character_count < 4:
        coherence_score = 40
        coherence_feedback = "Too short to evaluate as a sentence. Aim for subject + verb + object."
        coherence_corrections = ["Add a subject (\u8ab0)", "Add a verb (\u505a\u4ec0\u9ebc)"]
    elif character_count < 8:
        coherence_score = 65
        coherence_feedback = "Short sentence. Make sure it has a subject and a verb."
        coherence_corrections = []
    else:
        coherence_score = 78
        coherence_feedback = "Sentence length is good. Check that each clause connects naturally."
        coherence_corrections = []

    # Pronunciation note from Praat data
    tone_pct = round(praat_tone_accuracy)
    fluency_pct = round(praat_fluency_score)
    if tone_pct >= 80 and fluency_pct >= 75:
        pron_score = 88
        pron_feedback = f"Tones and rhythm both sound strong ({tone_pct}% tone accuracy)."
    elif tone_pct >= 60:
        pron_score = 65
        pron_feedback = f"Tone accuracy {tone_pct}% \u2014 keep working on the weaker tones. Rhythm: {fluency_pct}%."
    elif tone_pct > 0:
        pron_score = 45
        pron_feedback = f"Tone accuracy {tone_pct}% \u2014 focus on the tones marked in the pitch chart."
    else:
        pron_score = 50
        pron_feedback = "Speak clearly and try to hold each syllable long enough for tone recognition."

    if praat_vowel_quality:
        pron_feedback += f" Vowel quality: {praat_vowel_quality}."

    practice_next = (
        f"Say the sentence again adding {missing_words[0]}."
        if missing_words else
        "Say the same sentence with a different time or place word."
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
