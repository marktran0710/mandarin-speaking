import json
import os
from typing import Dict, List

import httpx
from dotenv import load_dotenv
from pinyin_service import canonical_pinyin_tone3

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
GEMINI_FEEDBACK_MODEL = os.getenv("GEMINI_FEEDBACK_MODEL", "gemini-3.6-flash")
GROQ_FEEDBACK_MODEL = os.getenv("GROQ_FEEDBACK_MODEL", "openai/gpt-oss-120b")
GROQ_WHISPER_MODEL = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3")
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
    return canonical_pinyin_tone3(text)


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


def apply_feedback_quality_gate(
    feedback: Dict,
    quality: Dict,
    *,
    transcription: str = "",
    scene_vocabulary: str = "",
) -> Dict:
    """Make student-facing feedback obey deterministic evidence gates.

    Generative providers may suggest language coaching, but they do not get
    to decide whether an acoustic score is trustworthy.  This function is
    intentionally provider-agnostic and is applied as the final server-side
    step after Praat and optional ASR verification.
    """
    result = dict(feedback or {})
    result["quality"] = {
        "status": str(quality.get("status", "retry")),
        "confidence": float(quality.get("confidence", 0.0)),
        "can_score_pronunciation": bool(quality.get("can_score_pronunciation")),
        "can_score_content": bool(quality.get("can_score_content")),
        "reason_codes": [
            str(reason) for reason in (quality.get("reason_codes") or [])
        ],
    }

    can_score_pronunciation = result["quality"]["can_score_pronunciation"]
    can_score_content = result["quality"]["can_score_content"]
    safe_message = str(
        quality.get("student_message")
        or "This attempt could not be scored safely. Please record it again."
    )

    if not can_score_pronunciation:
        result["pronunciation_note"] = {
            "score": 0,
            "feedback": safe_message,
            "details": [],
            "judged": False,
            "confidence": 0.0,
            "basis": "insufficient_acoustic_evidence",
        }
    else:
        pronunciation = dict(result.get("pronunciation_note") or {})
        pronunciation["judged"] = True
        pronunciation["confidence"] = result["quality"]["confidence"]
        pronunciation["basis"] = "praat_acoustic_measurements"
        result["pronunciation_note"] = pronunciation

    scene_words = [word.strip() for word in scene_vocabulary.split(",") if word.strip()]
    if can_score_content:
        # The LLM may phrase the explanation, but used/missing and the score
        # come from exact-or-pinyin matching against the transcript.
        used = [word for word in scene_words if _word_matches_phonetically(word, transcription)]
        missing = [word for word in scene_words if word not in used]
        vocabulary = dict(result.get("vocabulary_coverage") or {})
        if scene_words:
            vocabulary["score"] = round(len(used) / len(scene_words) * 100)
            vocabulary["used"] = used
            vocabulary["missing"] = missing
        vocabulary["judged"] = True
        vocabulary["basis"] = "deterministic_transcript_match"
        vocabulary["confidence"] = result["quality"]["confidence"]
        result["vocabulary_coverage"] = vocabulary
    else:
        result["vocabulary_coverage"] = {
            "score": 0,
            "used": [],
            "missing": scene_words,
            "feedback": safe_message,
            "judged": False,
            "confidence": 0.0,
            "basis": "insufficient_transcript_evidence",
        }
        result["coherence"] = {
            "score": 0,
            "feedback": safe_message,
            "corrections": [],
            "judged": False,
            "confidence": 0.0,
        }
        result["content_accuracy"] = {
            "score": 0,
            "feedback": "",
            "matched_details": [],
            "missed_details": [],
            "accepted": False,
            "judged": False,
            "confidence": 0.0,
            "requires_teacher_review": False,
        }
        result["corrective_feedback"] = _corrective_feedback_placeholder()
        result["improved_version"] = ""
        result["practice_prompt"] = safe_message

    # Vision/semantic judgments remain coaching suggestions, never a
    # high-stakes source of truth.  Expose that contract in the payload so
    # clients cannot accidentally present an LLM estimate as teacher-verified.
    content_accuracy = result.get("content_accuracy")
    if isinstance(content_accuracy, dict) and content_accuracy.get("judged"):
        content_accuracy["confidence"] = "limited"
        content_accuracy["requires_teacher_review"] = True
        content_accuracy["basis"] = "ai_semantic_estimate"

    return result


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
    scene_phrases: str = "",
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
                "feedback": "Record a sentence to get pronunciation feedback.",
                "details": [],
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

    # ── Pronunciation: tone-contour proxy for Goodness of Pronunciation ─────
    # Built as separate {key, text} entries — one per card the frontend shows
    # below the scene image — instead of one concatenated paragraph. The
    # joined "feedback" string is kept for callers that still want flat text.
    tone_pct = round(praat_tone_accuracy)
    fluency_pct = round(praat_fluency_score)
    pron_details: List[Dict] = []
    if tone_pct >= 80 and fluency_pct >= 75:
        pron_score = 88
        tone_text = f"Tones sound strong ({tone_pct}% tone-contour match)."
    elif tone_pct >= 60:
        pron_score = 65
        tone_text = f"Tone-contour match {tone_pct}% — keep working on the weaker tones."
    elif tone_pct > 0:
        pron_score = 45
        tone_text = f"Tone-contour match {tone_pct}% — focus on the tones marked in the pitch chart."
    else:
        pron_score = 50
        tone_text = "Speak clearly and hold each syllable long enough for tone recognition."
    pron_details.append({"key": "tone", "text": tone_text})

    if praat_pause_analysis is not None:
        fluency = caf_metrics.fluency_metrics(
            praat_speech_rate, praat_pause_analysis, character_count
        )
        rate_verdict = caf_metrics.speech_rate_verdict(fluency["articulation_rate"])
        pron_details.append({
            "key": "rhythm_pace",
            "text": f"{rate_verdict['text']} (mean run {fluency['mean_length_of_run']} syllables.)",
        })

        reference_text = scene_suggested_answer.strip() or text
        pause_result = caf_metrics.classify_pauses(
            reference_text, praat_pause_analysis, word_prosody or []
        )
        if pause_result["judged"] and pause_result["choppy"]:
            worst = max(pause_result["choppy"], key=lambda p: p["duration"])
            pron_details.append({
                "key": "pausing",
                "text": (
                    f"You paused between {worst['before']} and {worst['after']} — "
                    "try saying these together without a gap."
                ),
            })
        elif pause_result["judged"] and pause_result["natural"] and not pause_result["choppy"]:
            pron_details.append({
                "key": "pausing",
                "text": "Your pauses landed in natural spots — good phrasing.",
            })
    if praat_vowel_quality:
        pron_details.append({"key": "vowel_quality", "text": praat_vowel_quality})
    stress_note = _word_stress_note(word_prosody)
    if stress_note:
        pron_details.append({"key": "word_stress", "text": f"{stress_note}."})

    pron_feedback = " ".join(d["text"] for d in pron_details)

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
        elif scene_phrases.strip():
            corrective_hint = f"Try using one of these phrases in your sentence: {scene_phrases.strip()}"
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
            "details": pron_details,
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
