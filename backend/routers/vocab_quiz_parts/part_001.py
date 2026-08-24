from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from psycopg.types.json import Jsonb

import auth
import threading
from analytics.joint_time import fit_joint_mode
from analytics.weak_words import WordOccurrence, score_weak_words
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
_irt_refit_lock = threading.Lock()
_irt_refit_pending = False
_irt_refit_dirty = False


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


def _vocab_quiz_item_key(story_id: str, word: str) -> str:
    return f"{story_id}:{word}"


def _stored_quiz_item_key(story_id: str, result: dict, word: str) -> str:
    """Prefer the stable client identity, with a safe legacy fallback."""
    item_id = result.get("itemId")
    return item_id.strip() if isinstance(item_id, str) and item_id.strip() else _vocab_quiz_item_key(story_id, word)


def _load_vocab_quiz_irt_cache(db) -> Optional[dict]:
    row = db.execute(
        "SELECT student_ability, item_difficulty, student_speed, item_time_intensity "
        "FROM vocab_quiz_irt_cache WHERE id = 1"
    ).fetchone()
    return dict(row) if row else None


def refit_vocab_quiz_irt_cache() -> None:
    """Refits the ability/difficulty/speed/time-intensity model over every
    vocab-quiz attempt ever recorded (all students, all stories, all
    modes pooled — see analytics/joint_time.py for why pooling modes is a
    simplification, not a design decision) and caches the result.

    Runs as a background task after an attempt is written, so a student's
    own quiz submission never waits on a full model refit; the next
    weak-words read picks up the new fit. Deliberately a full refit every
    time rather than an incremental update — simplest correct thing for a
    single-class dataset size; revisit if this ever gets slow.
    """
    with connect_db() as db:
        rows = db.execute(
            "SELECT story_id, student_id, student_name, question_results FROM vocab_quiz_attempts"
        ).fetchall()

        responses = []
        for row in rows:
            student_key = row["student_id"] or row["student_name"]
            if not student_key:
                continue
            for result in row["question_results"] or []:
                word = result.get("word")
                if word is None:
                    continue
                responses.append((
                    student_key,
                    _stored_quiz_item_key(row["story_id"], result, word),
                    bool(result.get("correct")),
                    float(result.get("timeMs") or 0),
                ))

        if not responses:
            return

        fit = fit_joint_mode("all", responses)

        db.execute(
            """
            INSERT INTO vocab_quiz_irt_cache
                (id, student_ability, item_difficulty, student_speed, item_time_intensity,
                 n_responses, fitted_at)
            VALUES (1, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                student_ability = EXCLUDED.student_ability,
                item_difficulty = EXCLUDED.item_difficulty,
                student_speed = EXCLUDED.student_speed,
                item_time_intensity = EXCLUDED.item_time_intensity,
                n_responses = EXCLUDED.n_responses,
                fitted_at = EXCLUDED.fitted_at
            """,
            (
                Jsonb(fit.student_ability),
                Jsonb(fit.item_difficulty),
                Jsonb(fit.student_speed),
                Jsonb(fit.item_time_intensity),
                fit.n_responses,
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def _coalesced_irt_refit() -> None:
    """Run one refit at a time and fold concurrent submissions together."""
    global _irt_refit_pending, _irt_refit_dirty
    while True:
        with _irt_refit_lock:
            _irt_refit_dirty = False
        try:
            refit_vocab_quiz_irt_cache()
        finally:
            with _irt_refit_lock:
                if not _irt_refit_dirty:
                    _irt_refit_pending = False
                    return


def schedule_irt_refit(background_tasks: BackgroundTasks) -> None:
    """Schedule a bounded/coalesced cache refresh after a quiz write."""
    global _irt_refit_pending, _irt_refit_dirty
    with _irt_refit_lock:
        _irt_refit_dirty = True
        if _irt_refit_pending:
            return
        _irt_refit_pending = True
    background_tasks.add_task(_coalesced_irt_refit)


@router.get("/api/vocab-quiz-attempts/weak-words")
async def get_weak_words(
    story_id: str,
    identity: auth.Identity = Depends(auth.require_student),
):
    """
    Words in this story that still need review for this student, ranked by
    a score combining four signals: this student's overall ability vs. the
    word's own difficulty (from the cached joint IRT fit), their recency-
    weighted accuracy on the word across every past attempt (not just the
    latest), and whether their correct answers on it run slower than their
    own norm. A word wrong on the most recent attempt is always included —
    that floor never regresses versus the old "wrong last time" behavior;
    the model can additionally surface a word that was answered *correctly*
    last time but looks fragile on the combined signal. See
    analytics/weak_words.py for the scoring itself.
    """
    student_key = identity.id

    query = (
        "SELECT question_results FROM vocab_quiz_attempts "
        "WHERE story_id = %s AND student_id = %s ORDER BY completed_at ASC"
    )
    params: list = [story_id, identity.id]

    with connect_db() as db:
        rows = db.execute(query, params).fetchall()

        occurrences_by_word: dict = defaultdict(list)
        item_keys_by_word: dict = defaultdict(set)
        for row in rows:
            for result in row["question_results"] or []:
                word = result.get("word")
                if word is None:
                    continue
                item_keys_by_word[word].add(_stored_quiz_item_key(story_id, result, word))
                occurrences_by_word[word].append(
                    WordOccurrence(
                        correct=bool(result.get("correct")),
                        time_ms=int(result.get("timeMs") or 0),
                    )
                )

        if not occurrences_by_word:
            return {"words": []}

        fit = _load_vocab_quiz_irt_cache(db)

    if fit is None:
        # No model fit yet (e.g. this is the very first attempt ever
        # recorded) — fall back to the original, simpler "wrong on the
        # most recent attempt" rule rather than block on a fit.
        weak = [word for word, occs in occurrences_by_word.items() if not occs[-1].correct]
        return {"words": weak}

    def mean_fitted_value(values: dict, keys: set[str]) -> float:
        fitted = [float(values[key]) for key in keys if key in values]
        return sum(fitted) / len(fitted) if fitted else 0.0

    difficulty_by_word = {
        word: mean_fitted_value(fit["item_difficulty"], item_keys_by_word[word])
        for word in occurrences_by_word
    }
    time_intensity_by_word = {
        word: mean_fitted_value(fit["item_time_intensity"], item_keys_by_word[word])
        for word in occurrences_by_word
    }
    ability = fit["student_ability"].get(student_key, 0.0)
    speed = fit["student_speed"].get(student_key, 0.0)

    scores = score_weak_words(
        occurrences_by_word, ability, speed, difficulty_by_word, time_intensity_by_word
    )
    weak = [s.word for s in sorted(scores, key=lambda s: s.weak_score, reverse=True) if s.weak]
    return {"words": weak}


@router.post("/api/vocab-quiz-attempts")
async def create_vocab_quiz_attempt(
    attempt: VocabQuizAttemptRequest,
    background_tasks: BackgroundTasks,
    identity: auth.Identity = Depends(auth.require_student),
):
    attempt.studentId = identity.id
    with connect_db() as db:
        existing = db.execute(
            "SELECT student_id FROM vocab_quiz_attempts WHERE id = %s",
            (attempt.id,),
        ).fetchone()
        if existing is not None and existing.get("student_id") != identity.id:
            raise HTTPException(
                status_code=409,
                detail="Quiz attempt already belongs to another student.",
            )
        db.execute(
            """
            INSERT INTO vocab_quiz_attempts
                (id, story_id, student_name, student_id, mode, completed_at,
                 total_questions, correct_count, total_time_ms, question_results)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                story_id = EXCLUDED.story_id,
                student_name = EXCLUDED.student_name,
                student_id = EXCLUDED.student_id,
                mode = EXCLUDED.mode,
                completed_at = EXCLUDED.completed_at,
                total_questions = EXCLUDED.total_questions,
                correct_count = EXCLUDED.correct_count,
                total_time_ms = EXCLUDED.total_time_ms,
                question_results = EXCLUDED.question_results
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
                Jsonb([r.model_dump(exclude_none=True) for r in attempt.questionResults]),
            ),
        )
    schedule_irt_refit(background_tasks)
    return attempt.model_dump(exclude_none=True)


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
