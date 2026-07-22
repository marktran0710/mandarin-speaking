import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from database import connect_db, row_to_vocab_quiz_attempt
import main
from main import (
    PhraseFromSentenceRequest,
    PhraseFromSentenceResponse,
    VocabClozeRequest,
    VocabClozeResponse,
    VocabDistractorRequest,
    VocabDistractorResponse,
    VocabFromSentenceRequest,
    VocabFromSentenceResponse,
    VocabLookalikeRequest,
    VocabLookalikeResponse,
    VocabQuizAttemptRequest,
    VocabSynonymRequest,
    VocabSynonymResponse,
)

router = APIRouter()


@router.get("/api/vocab-quiz-attempts")
async def list_vocab_quiz_attempts(
    story_id: Optional[str] = None,
    student_name: Optional[str] = None,
    student_id: Optional[str] = None,
):
    query = "SELECT * FROM vocab_quiz_attempts WHERE 1=1"
    params: list = []
    if story_id:
        query += " AND story_id = ?"
        params.append(story_id)
    if student_name:
        query += " AND student_name = ?"
        params.append(student_name)
    if student_id:
        query += " AND student_id = ?"
        params.append(student_id)
    query += " ORDER BY completed_at DESC"

    with connect_db() as db:
        rows = db.execute(query, params).fetchall()
    return [row_to_vocab_quiz_attempt(row) for row in rows]


@router.get("/api/vocab-quiz-attempts/weak-words")
async def get_weak_words(
    story_id: str,
    student_id: Optional[str] = None,
    student_name: Optional[str] = None,
):
    """
    Words in this story whose most recent answer (across every past attempt,
    any mode) was wrong — lets the quiz mode-select screen offer a
    persistent "practice what you still get wrong" round instead of only
    the same-session retry. A word answered wrong once but right in a later
    attempt is not weak; ordering is by completed_at desc across attempts,
    and by result order (last occurrence wins) within an attempt.
    """
    if not student_id and not student_name:
        raise HTTPException(status_code=400, detail="Provide student_id or student_name.")

    query = "SELECT question_results FROM vocab_quiz_attempts WHERE story_id = ?"
    params: list = [story_id]
    if student_id:
        query += " AND student_id = ?"
        params.append(student_id)
    else:
        query += " AND student_name = ?"
        params.append(student_name)
    query += " ORDER BY completed_at DESC"

    with connect_db() as db:
        rows = db.execute(query, params).fetchall()

    resolved: dict[str, bool] = {}
    for row in rows:
        results = json.loads(row["question_results"] or "[]")
        for result in reversed(results):
            word = result.get("word")
            if word is None or word in resolved:
                continue
            resolved[word] = bool(result.get("correct"))

    return {"words": [word for word, correct in resolved.items() if not correct]}


@router.post("/api/vocab-quiz-attempts")
async def create_vocab_quiz_attempt(attempt: VocabQuizAttemptRequest):
    with connect_db() as db:
        db.execute(
            """
            INSERT OR REPLACE INTO vocab_quiz_attempts
                (id, story_id, student_name, student_id, mode, completed_at,
                 total_questions, correct_count, total_time_ms, question_results)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                attempt.id,
                attempt.storyId,
                attempt.studentName,
                attempt.studentId,
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


@router.post("/api/phrases-from-sentence", response_model=PhraseFromSentenceResponse)
async def phrases_from_sentence(request: PhraseFromSentenceRequest, req: Request):
    """
    Extract handy, reusable phrase-level chunks (not single words, not the
    whole sentence) from a scene's suggested-answer sentence — lets a
    teacher autofill the phrases table instead of typing them by hand.
    """
    client_ip = req.client.host if req.client else "unknown"
    main._check_rate_limit(f"phrases-from-sentence:{client_ip}", max_requests=10, window_seconds=60)

    sentence = request.sentence.strip()
    if not sentence:
        raise HTTPException(status_code=400, detail="Provide a sentence to extract phrases from.")
    count = max(1, request.count)

    engines = [
        ("groq", main.GROQ_API_KEY, main.extract_phrases_from_sentence_with_groq),
        ("gemini", main.GEMINI_API_KEY, main.extract_phrases_from_sentence_with_gemini),
    ]
    if not any(key for _, key, _ in engines):
        raise HTTPException(
            status_code=503,
            detail="AI phrase extraction requires GROQ_API_KEY or GEMINI_API_KEY to be configured on the backend.",
        )

    last_error: Exception | None = None
    for name, key, extract in engines:
        if not key:
            continue
        try:
            phrases = await extract(sentence, count)
        except Exception as exc:
            main.logger.warning("%s phrase extraction failed, trying next engine: %s", name, exc)
            last_error = exc
            continue
        return PhraseFromSentenceResponse(phrases=phrases)

    raise HTTPException(
        status_code=502,
        detail="Could not extract phrases from that sentence.",
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


@router.post("/api/vocab-quiz-cloze", response_model=VocabClozeResponse)
async def vocab_quiz_cloze(request: VocabClozeRequest, req: Request):
    """
    Generate fill-in-the-blank (cloze) questions for the vocabulary quiz: a
    natural example sentence per word plus plausible wrong-word options —
    an alternative to the word->translation multiple-choice question, mixed
    in for variety (see StoryVocabQuiz's weak_words-adjacent cloze mixing).
    """
    client_ip = req.client.host if req.client else "unknown"
    main._check_rate_limit(f"vocab-quiz-cloze:{client_ip}", max_requests=10, window_seconds=60)

    words = [w for w in request.words if w.word.strip() and w.translation.strip()]
    if not words:
        raise HTTPException(status_code=400, detail="Provide at least one word with a translation.")

    engines = [
        ("groq", main.GROQ_API_KEY, main.generate_vocab_cloze_with_groq),
        ("gemini", main.GEMINI_API_KEY, main.generate_vocab_cloze_with_gemini),
    ]
    if not any(key for _, key, _ in engines):
        raise HTTPException(
            status_code=503,
            detail="AI cloze generation requires GROQ_API_KEY or GEMINI_API_KEY to be configured on the backend.",
        )

    last_error: Exception | None = None
    for name, key, generate in engines:
        if not key:
            continue
        try:
            results = await generate(words)
        except Exception as exc:
            main.logger.warning("%s cloze generation failed, trying next engine: %s", name, exc)
            last_error = exc
            continue
        return VocabClozeResponse(results=results)

    raise HTTPException(
        status_code=502,
        detail="Could not generate cloze questions for these words.",
    ) from last_error


@router.post("/api/vocab-quiz-lookalike", response_model=VocabLookalikeResponse)
async def vocab_quiz_lookalike(request: VocabLookalikeRequest, req: Request):
    """
    Generate visually-confusable Traditional Chinese words (喝/渴, 買/賣) for
    each of a story's vocabulary words — the tier-3 quiz's face-confusion
    traps, mixed into reverse/listening question options. Same generate-once,
    cache-per-story flow as the distractor/cloze/synonym endpoints above.
    """
    client_ip = req.client.host if req.client else "unknown"
    main._check_rate_limit(f"vocab-quiz-lookalike:{client_ip}", max_requests=10, window_seconds=60)

    words = [w for w in request.words if w.word.strip() and w.translation.strip()]
    if not words:
        raise HTTPException(status_code=400, detail="Provide at least one word with a translation.")

    engines = [
        ("groq", main.GROQ_API_KEY, main.generate_vocab_lookalike_with_groq),
        ("gemini", main.GEMINI_API_KEY, main.generate_vocab_lookalike_with_gemini),
    ]
    if not any(key for _, key, _ in engines):
        raise HTTPException(
            status_code=503,
            detail="AI look-alike generation requires GROQ_API_KEY or GEMINI_API_KEY to be configured on the backend.",
        )

    last_error: Exception | None = None
    for name, key, generate in engines:
        if not key:
            continue
        try:
            results = await generate(words)
        except Exception as exc:
            main.logger.warning("%s look-alike generation failed, trying next engine: %s", name, exc)
            last_error = exc
            continue
        return VocabLookalikeResponse(results=results)

    raise HTTPException(
        status_code=502,
        detail="Could not generate look-alike traps for these words.",
    ) from last_error


@router.post("/api/vocab-quiz-synonym", response_model=VocabSynonymResponse)
async def vocab_quiz_synonym(request: VocabSynonymRequest, req: Request):
    """
    Generate "which word means the same?" questions for the vocabulary quiz:
    a real Chinese synonym per word plus plausible non-synonym distractors —
    another alternative question shape mixed in alongside translation/cloze.
    """
    client_ip = req.client.host if req.client else "unknown"
    main._check_rate_limit(f"vocab-quiz-synonym:{client_ip}", max_requests=10, window_seconds=60)

    words = [w for w in request.words if w.word.strip() and w.translation.strip()]
    if not words:
        raise HTTPException(status_code=400, detail="Provide at least one word with a translation.")

    engines = [
        ("groq", main.GROQ_API_KEY, main.generate_vocab_synonym_with_groq),
        ("gemini", main.GEMINI_API_KEY, main.generate_vocab_synonym_with_gemini),
    ]
    if not any(key for _, key, _ in engines):
        raise HTTPException(
            status_code=503,
            detail="AI synonym generation requires GROQ_API_KEY or GEMINI_API_KEY to be configured on the backend.",
        )

    last_error: Exception | None = None
    for name, key, generate in engines:
        if not key:
            continue
        try:
            results = await generate(words)
        except Exception as exc:
            main.logger.warning("%s synonym generation failed, trying next engine: %s", name, exc)
            last_error = exc
            continue
        return VocabSynonymResponse(results=results)

    raise HTTPException(
        status_code=502,
        detail="Could not generate synonym questions for these words.",
    ) from last_error
