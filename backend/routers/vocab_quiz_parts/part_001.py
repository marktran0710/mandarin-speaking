from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from psycopg.types.json import Jsonb

import auth
from analytics.bkt_question_validation import classify_bkt_response, validate_vocabulary_question
from analytics.bkt_mastery import (
    diagnostic_status,
    get_priority_review_words,
    get_vocabulary_mastery,
    record_attempt_and_rebuild,
    seen_item_ids,
)
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
    VocabQuizAttemptRequest,
    VocabSynonymRequest,
    VocabSynonymResponse,
)

router = APIRouter(dependencies=[Depends(auth.get_current_identity)])


@router.get("/api/vocab-quiz-attempts")
async def list_vocab_quiz_attempts(
    story_id: Optional[str] = None,
    student_name: Optional[str] = None,
    student_id: Optional[str] = None,
    identity: auth.Identity = Depends(auth.get_current_identity),
):
    if identity.role == "student":
        student_id, student_name = identity.id, None

    query = "SELECT * FROM vocab_quiz_attempts WHERE 1=1"
    params: list = []
    if story_id:
        query += " AND story_id = %s"
        params.append(story_id)
    if student_name:
        query += " AND student_name = %s"
        params.append(student_name)
    if student_id:
        query += " AND student_id = %s"
        params.append(student_id)
    query += " ORDER BY completed_at DESC"

    with connect_db() as db:
        rows = db.execute(query, params).fetchall()
    return [row_to_vocab_quiz_attempt(row) for row in rows]


def _assert_student_scope(identity: auth.Identity, student_id: str) -> None:
    if identity.role == "student" and identity.id != student_id:
        raise HTTPException(status_code=403, detail="Students may only view their own vocabulary mastery.")


@router.get("/api/students/{student_id}/weak-words")
async def get_student_priority_review_words(
    student_id: str,
    review_count: Optional[int] = None,
    story_id: Optional[str] = None,
    identity: auth.Identity = Depends(auth.get_current_identity),
):
    """Return learner-relative Bottom-K BKT review priorities."""
    _assert_student_scope(identity, student_id)
    options = {key: value for key, value in (("reviewCount", review_count), ("storyId", story_id)) if value is not None}
    with connect_db() as db:
        return get_priority_review_words(db, student_id, options)


@router.get("/api/students/{student_id}/vocabulary-mastery")
async def get_student_vocabulary_mastery(
    student_id: str,
    identity: auth.Identity = Depends(auth.get_current_identity),
):
    _assert_student_scope(identity, student_id)
    with connect_db() as db:
        return {
            **diagnostic_status(db, student_id),
            "words": get_vocabulary_mastery(db, student_id),
        }


@router.get("/api/students/{student_id}/vocabulary-mastery/{word_id:path}/seen-items")
async def get_seen_vocabulary_items(
    student_id: str,
    word_id: str,
    identity: auth.Identity = Depends(auth.get_current_identity),
):
    _assert_student_scope(identity, student_id)
    with connect_db() as db:
        return {"itemIds": seen_item_ids(db, student_id, word_id)}


@router.get("/api/vocab-quiz-attempts/weak-words")
async def get_weak_words(
    story_id: str,
    identity: auth.Identity = Depends(auth.require_student),
):
    """Compatibility-shaped response backed by guarded standard BKT."""
    with connect_db() as db:
        result = get_priority_review_words(db, identity.id, {"storyId": story_id})
    return {
        "words": [word["word"] for word in result["words"]],
        "diagnostic": {
            key: result[key]
            for key in ("unlocked", "requiredDiagnosticQuizzes", "completedDiagnosticQuizzes")
        },
    }


@router.post("/api/vocab-quiz-attempts")
async def create_vocab_quiz_attempt(
    attempt: VocabQuizAttemptRequest,
    identity: auth.Identity = Depends(auth.require_student),
):
    attempt.studentId = identity.id
    raw_question_results = [result.model_dump(exclude_none=True, exclude_defaults=True) for result in attempt.questionResults]
    question_results = []
    for result in attempt.questionResults:
        payload = result.model_dump(exclude_none=True, exclude_defaults=True)
        # Re-run the content contract on the server. The client may send a
        # hint, but it cannot make an otherwise malformed or non-approved
        # response eligible by setting ``isBktEligible`` itself.
        question_for_validation = {
            "questionId": payload.get("itemId"),
            "wordId": payload.get("conceptId") or payload.get("word"),
            "targetWordIds": [payload.get("conceptId") or payload.get("word")],
            "questionKind": payload.get("questionKind"),
            "correctAnswer": payload.get("correctAnswer"),
            "options": payload.get("presentedOptions"),
            "prompt": payload.get("questionPrompt"),
            "validationStatus": payload.get("bktValidationStatus"),
        }
        question_quality = validate_vocabulary_question(question_for_validation)
        candidate = {**payload, "isBktEligible": question_quality.eligible_for_bkt}
        eligible, reasons = classify_bkt_response(candidate, attempt)
        if question_quality.errors:
            reasons = list(dict.fromkeys(reasons + [issue["code"] for issue in question_quality.errors]))
            eligible = False
        payload["isBktEligible"] = eligible
        payload["bktEligibilityErrors"] = reasons
        if not eligible:
            main.logger.warning(
                "BKT_UPDATE_SKIPPED question_id=%s reason=%s",
                payload.get("itemId") or payload.get("word") or "unknown",
                ",".join(reasons),
            )
        question_results.append(payload)
    with connect_db() as db:
        existing = db.execute(
            "SELECT * FROM vocab_quiz_attempts WHERE id = %s",
            (attempt.id,),
        ).fetchone()
        if existing is not None and existing.get("student_id") != identity.id:
            raise HTTPException(
                status_code=409,
                detail="Quiz attempt already belongs to another student.",
            )
        if existing is not None:
            same_attempt = all([
                existing.get("story_id") == attempt.storyId,
                existing.get("student_name") == attempt.studentName,
                existing.get("mode") == attempt.mode,
                existing.get("completed_at") == attempt.completedAt,
                existing.get("total_questions") == attempt.totalQuestions,
                existing.get("correct_count") == attempt.correctCount,
                existing.get("total_time_ms") == attempt.totalTimeMs,
                (existing.get("question_results") or []) == raw_question_results,
            ])
            if not same_attempt:
                raise HTTPException(
                    status_code=409,
                    detail="Quiz attempt already exists with different response data.",
                )
        db.execute(
            """
            INSERT INTO vocab_quiz_attempts
                (id, story_id, student_name, student_id, mode, completed_at,
                 total_questions, correct_count, total_time_ms, question_results)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
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
                Jsonb(raw_question_results),
            ),
        )
        # JSONB remains the client-facing attempt source of truth, while this
        # normalized ledger makes every response replayable for BKT calibration.
        normalized_attempt = attempt.model_dump(exclude_none=True)
        normalized_attempt["questionResults"] = question_results
        record_attempt_and_rebuild(db, normalized_attempt, identity.id, response_results=question_results)
    payload = attempt.model_dump(exclude_none=True)
    payload["questionResults"] = raw_question_results
    # Keep the nullable field present for clients that use the response as a
    # round-trip representation of an attempt without a selected mode.
    payload.setdefault("mode", attempt.mode)
    return payload


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
