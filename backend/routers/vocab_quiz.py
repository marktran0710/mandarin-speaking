import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from database import connect_db, row_to_vocab_quiz_attempt
import main
from main import (
    VocabDistractorRequest,
    VocabDistractorResponse,
    VocabFromSentenceRequest,
    VocabFromSentenceResponse,
    VocabQuizAttemptRequest,
)

router = APIRouter()


@router.get("/api/vocab-quiz-attempts")
async def list_vocab_quiz_attempts(
    story_id: Optional[str] = None,
    student_name: Optional[str] = None,
):
    query = "SELECT * FROM vocab_quiz_attempts WHERE 1=1"
    params: list = []
    if story_id:
        query += " AND story_id = ?"
        params.append(story_id)
    if student_name:
        query += " AND student_name = ?"
        params.append(student_name)
    query += " ORDER BY completed_at DESC"

    with connect_db() as db:
        rows = db.execute(query, params).fetchall()
    return [row_to_vocab_quiz_attempt(row) for row in rows]


@router.post("/api/vocab-quiz-attempts")
async def create_vocab_quiz_attempt(attempt: VocabQuizAttemptRequest):
    with connect_db() as db:
        db.execute(
            """
            INSERT OR REPLACE INTO vocab_quiz_attempts
                (id, story_id, student_name, mode, completed_at, total_questions,
                 correct_count, total_time_ms, question_results)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                attempt.id,
                attempt.storyId,
                attempt.studentName,
                attempt.mode,
                attempt.completedAt,
                attempt.totalQuestions,
                attempt.correctCount,
                attempt.totalTimeMs,
                json.dumps([r.model_dump() for r in attempt.questionResults]),
            ),
        )
    return attempt.model_dump()


@router.post("/api/vocab-from-sentence", response_model=VocabFromSentenceResponse)
async def vocab_from_sentence(request: VocabFromSentenceRequest, req: Request):
    """
    Segment a Chinese sentence (typically a scene's "suggested answer") into
    its key vocabulary, with pinyin, part of speech, and English translation
    for each word — lets a teacher autofill a scene's vocabulary table instead
    of retyping/retranslating words that are already in the sentence.
    """
    client_ip = req.client.host if req.client else "unknown"
    main._check_rate_limit(f"vocab-from-sentence:{client_ip}", max_requests=10, window_seconds=60)

    sentence = request.sentence.strip()
    if not sentence:
        raise HTTPException(status_code=400, detail="Provide a sentence to extract vocabulary from.")

    # Groq first (fast, free tier, and its JSON mode avoids the markdown-fence
    # parsing failures the Gemini path is prone to), falling back to Gemini —
    # same "try each configured provider in order" pattern as the pronunciation
    # feedback engines in ai_feedback.py.
    engines = [
        ("groq", main.GROQ_API_KEY, main.extract_vocab_from_sentence_with_groq),
        ("gemini", main.GEMINI_API_KEY, main.extract_vocab_from_sentence_with_gemini),
    ]
    if not any(key for _, key, _ in engines):
        raise HTTPException(
            status_code=503,
            detail="AI vocabulary extraction requires GROQ_API_KEY or GEMINI_API_KEY to be configured on the backend.",
        )

    last_error: Exception | None = None
    for name, key, extract in engines:
        if not key:
            continue
        try:
            words = await extract(sentence)
        except Exception as exc:
            main.logger.warning("%s vocab extraction failed, trying next engine: %s", name, exc)
            last_error = exc
            continue
        return VocabFromSentenceResponse(words=words)

    raise HTTPException(
        status_code=502,
        detail="Could not extract vocabulary from that sentence.",
    ) from last_error


@router.post("/api/vocab-quiz-distractors", response_model=VocabDistractorResponse)
async def vocab_quiz_distractors(request: VocabDistractorRequest, req: Request):
    """
    Generate plausible-but-wrong English translations for each of a story's
    vocabulary words, for the pre-practice vocabulary quiz's multiple-choice
    options. Real distractors (near-synonyms, same part of speech, common
    learner mix-ups) make students actually discriminate meaning instead of
    eliminating obviously-unrelated filler words — generated once per story
    and cached by the caller, not regenerated per student attempt.
    """
    client_ip = req.client.host if req.client else "unknown"
    main._check_rate_limit(f"vocab-quiz-distractors:{client_ip}", max_requests=10, window_seconds=60)

    words = [w for w in request.words if w.word.strip() and w.translation.strip()]
    if not words:
        raise HTTPException(status_code=400, detail="Provide at least one word with a translation.")

    engines = [
        ("groq", main.GROQ_API_KEY, main.generate_vocab_distractors_with_groq),
        ("gemini", main.GEMINI_API_KEY, main.generate_vocab_distractors_with_gemini),
    ]
    if not any(key for _, key, _ in engines):
        raise HTTPException(
            status_code=503,
            detail="AI distractor generation requires GROQ_API_KEY or GEMINI_API_KEY to be configured on the backend.",
        )

    last_error: Exception | None = None
    for name, key, generate in engines:
        if not key:
            continue
        try:
            results = await generate(words)
        except Exception as exc:
            main.logger.warning("%s distractor generation failed, trying next engine: %s", name, exc)
            last_error = exc
            continue
        return VocabDistractorResponse(results=results)

    raise HTTPException(
        status_code=502,
        detail="Could not generate quiz distractors for these words.",
    ) from last_error
