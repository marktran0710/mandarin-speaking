

def _rhythm_pace_dimension(avg_fluency_score: float, avg_articulation_rate: float) -> Dict:
    if avg_fluency_score <= 0:
        return {
            "score": 0,
            "feedback": "No pacing data was available for this story.",
            "judged": False,
        }
    rate_note = (
        caf_metrics.speech_rate_verdict(avg_articulation_rate)["text"]
        if avg_articulation_rate > 0
        else f"Your pacing scored {round(avg_fluency_score)}% overall."
    )
    return {
        "score": max(0, min(100, round(avg_fluency_score))),
        "feedback": rate_note,
        "judged": True,
    }


def _pausing_dimension(
    total_pause_count: float,
    longest_single_pause: float,
    total_utterance_count: float,
    scene_count: int,
    total_choppy_pause_count: float,
) -> Dict:
    has_data = total_pause_count > 0 or total_utterance_count > 0 or longest_single_pause > 0
    if not has_data:
        return {
            "score": 0,
            "feedback": "No pause data was available for this story.",
            "judged": False,
        }
    avg_pauses_per_scene = total_pause_count / max(1, scene_count)
    note = (
        f"You paused {round(total_pause_count)} time"
        f"{'s' if round(total_pause_count) != 1 else ''} across the story "
        f"({avg_pauses_per_scene:.1f} per scene)"
    )
    if longest_single_pause >= 0.8:
        note += f", including a {longest_single_pause:.1f}s gap at the longest point"
    note += ". "
    if total_choppy_pause_count > 0:
        note += (
            f"{round(total_choppy_pause_count)} of those pause"
            f"{'s' if round(total_choppy_pause_count) != 1 else ''} broke up a phrase rather than "
            "landing at a comma or clause break — try running the sentence through your head once "
            "before recording so you don't need to stop mid-phrase."
        )
    else:
        note += "Keep chunking your pauses at natural phrase breaks like that."

    longest_penalty = 20 if longest_single_pause >= 1.5 else (10 if longest_single_pause >= 0.8 else 0)
    score = round(100 - avg_pauses_per_scene * 12 - longest_penalty - total_choppy_pause_count * 6)
    return {"score": max(0, min(100, score)), "feedback": note, "judged": True}


def fallback_story_feedback(
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
) -> Dict:
    """Offline story-level feedback — no LLM call.

    Four pronunciation-focused dimensions — tone, word_stress, rhythm_pace,
    pausing — mirroring the same four axes the frontend's radar chart already
    draws straight from Praat data. Not the old IELTS-style vocabulary/grammar
    pillars: once a scene hands the student a script to read rather than
    compose freely, vocabulary/grammar choice isn't really being tested, only
    delivery is. If no Praat data is available at all for a dimension (e.g.
    no scene was ever analyzed), it falls back to a clearly-flagged
    placeholder (``judged: False``) instead of a false score.
    """
    return {
        "provider": "local",
        "tone": _tone_dimension(avg_tone_accuracy),
        "word_stress": _word_stress_dimension(avg_pron_score),
        "rhythm_pace": _rhythm_pace_dimension(avg_fluency_score, avg_articulation_rate),
        "pausing": _pausing_dimension(
            total_pause_count, longest_single_pause, total_utterance_count,
            scene_count, total_choppy_pause_count,
        ),
    }


def _normalize_story_feedback(
    data: Dict,
    avg_tone_accuracy: float = 0,
    avg_fluency_score: float = 0,
    avg_pron_score: float = 0,
    total_pause_count: float = 0,
    longest_single_pause: float = 0,
    total_utterance_count: float = 0,
    scene_count: int = 1,
    total_choppy_pause_count: float = 0,
    avg_articulation_rate: float = 0,
) -> Dict:
    fallback = fallback_story_feedback(
        "",
        avg_tone_accuracy=avg_tone_accuracy,
        avg_fluency_score=avg_fluency_score,
        avg_pron_score=avg_pron_score,
        total_pause_count=total_pause_count,
        longest_single_pause=longest_single_pause,
        total_utterance_count=total_utterance_count,
        scene_count=scene_count,
        total_choppy_pause_count=total_choppy_pause_count,
        avg_articulation_rate=avg_articulation_rate,
    )

    def _dimension(key: str) -> Dict:
        raw = data.get(key) or {}
        return {
            "score": _score(raw.get("score", fallback[key]["score"])),
            "feedback": str(raw.get("feedback", fallback[key]["feedback"])),
            "judged": True,
        }

    return {
        "provider": str(data.get("provider", "ai")),
        "tone": _dimension("tone"),
        "word_stress": _dimension("word_stress"),
        "rhythm_pace": _dimension("rhythm_pace"),
        "pausing": _dimension("pausing"),
    }


async def _story_feedback_with_groq(
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
) -> Dict:
    payload = {
        "model": GROQ_FEEDBACK_MODEL,
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": _STORY_FEEDBACK_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _story_feedback_prompt(
                    combined_transcript, avg_tone_accuracy, avg_fluency_score, avg_pron_score,
                    total_pause_count, longest_single_pause, total_utterance_count, scene_count,
                    total_choppy_pause_count, avg_articulation_rate,
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
    return _normalize_story_feedback(
        data, avg_tone_accuracy, avg_fluency_score, avg_pron_score,
        total_pause_count, longest_single_pause, total_utterance_count, scene_count,
        total_choppy_pause_count, avg_articulation_rate,
    )


async def _story_feedback_with_openai(
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
) -> Dict:
    payload = {
        "model": OPENAI_FEEDBACK_MODEL,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _STORY_FEEDBACK_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _story_feedback_prompt(
                    combined_transcript, avg_tone_accuracy, avg_fluency_score, avg_pron_score,
                    total_pause_count, longest_single_pause, total_utterance_count, scene_count,
                    total_choppy_pause_count, avg_articulation_rate,
                ),
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
    return _normalize_story_feedback(
        data, avg_tone_accuracy, avg_fluency_score, avg_pron_score,
        total_pause_count, longest_single_pause, total_utterance_count, scene_count,
        total_choppy_pause_count, avg_articulation_rate,
    )


async def _story_feedback_with_gemini(
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
) -> Dict:
    payload = {
        "system_instruction": {"parts": [{"text": _STORY_FEEDBACK_SYSTEM_PROMPT}]},
        "contents": [
            {
                "parts": [
                    {
                        "text": _story_feedback_prompt(
                            combined_transcript, avg_tone_accuracy, avg_fluency_score, avg_pron_score,
                            total_pause_count, longest_single_pause, total_utterance_count, scene_count,
                        )
                    }
                ]
            }
        ],
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
    return _normalize_story_feedback(
        data, avg_tone_accuracy, avg_fluency_score, avg_pron_score,
        total_pause_count, longest_single_pause, total_utterance_count, scene_count,
        total_choppy_pause_count, avg_articulation_rate,
    )


async def generate_story_feedback(
    combined_transcript: str,
    provider: str | None = None,
    avg_tone_accuracy: float = 0,
    avg_fluency_score: float = 0,
    avg_pron_score: float = 0,
    total_pause_count: float = 0,
    longest_single_pause: float = 0,
    total_utterance_count: float = 0,
    scene_count: int = 1,
    total_choppy_pause_count: float = 0,
    avg_articulation_rate: float = 0,
) -> Dict:
    """Produce one holistic, story-level feedback after all scenes are submitted.

    Mirrors the provider-dispatch-with-fallback shape of generate_language_feedback:
    the requested engine is tried first, then any other configured cloud provider,
    finally the offline CAF-based engine. Fluency-and-Coherence and Pronunciation
    are grounded in avg_tone_accuracy/avg_fluency_score/avg_pron_score (the
    per-scene Praat metrics, averaged across the story) plus the real pause/
    utterance counts (total_pause_count, longest_single_pause,
    total_utterance_count) — delivery data that matters more once a scene can
    hand the student a suggestedAnswer to read, since vocabulary/grammar
    aren't really a choice the student is making in that case, but how they
    deliver it (pausing, chunking into utterances) still is. Lexical Resource
    and Grammatical Range and Accuracy stay text-only in every engine.
    """
    text = combined_transcript.strip()
    praat_args = dict(
        avg_tone_accuracy=avg_tone_accuracy,
        avg_fluency_score=avg_fluency_score,
        avg_pron_score=avg_pron_score,
        total_pause_count=total_pause_count,
        longest_single_pause=longest_single_pause,
        total_utterance_count=total_utterance_count,
        scene_count=scene_count,
        total_choppy_pause_count=total_choppy_pause_count,
        avg_articulation_rate=avg_articulation_rate,
    )
    if not text:
        return fallback_story_feedback(text, **praat_args)

    chosen = (provider or AI_FEEDBACK_PROVIDER or "local").strip().lower()
    if chosen == "local":
        return fallback_story_feedback(text, **praat_args)

    all_providers = ["groq", "gemini", "openai"]
    order = [chosen] + [p for p in all_providers if p != chosen]
    callers = {
        "groq": _story_feedback_with_groq,
        "openai": _story_feedback_with_openai,
        "gemini": _story_feedback_with_gemini,
    }
    keys = {"groq": GROQ_API_KEY, "openai": OPENAI_API_KEY, "gemini": GEMINI_API_KEY}
    for name in order:
        if not keys.get(name):
            continue
        try:
            return await callers[name](text, **praat_args)
        except Exception as exc:
            print(f"{name} story feedback failed, trying next engine: {exc}")

    return fallback_story_feedback(text, **praat_args)
