from psycopg.types.json import Jsonb

import auth
from database import connect_db, row_to_speaking_progress
from main import SpeakingProgressRequest
from fastapi import APIRouter, Depends

router = APIRouter()

_RESULT_CORE_FIELDS = (
    "sceneIndex",
    "transcription",
    "vocabUsed",
    "vocabMissing",
    "vocabScore",
    "toneAccuracy",
    "pronScore",
    "fluencyScore",
    "pauseCount",
    "longestPause",
    "utteranceCount",
    "choppyPauseCount",
    "articulationRate",
)


def _merge_cleared_words(existing: object, incoming: list[str]) -> list[str]:
    """Keep the durable union so a stale save cannot undo a drill pass."""
    values: list[str] = []
    for word in [*(existing if isinstance(existing, list) else []), *incoming]:
        if isinstance(word, str) and word not in values:
            values.append(word)
    return values


def _merge_latest_result(existing: object, incoming: dict, *, same_attempt: bool) -> dict:
    """Merge same-attempt enrichment without erasing non-empty fields."""
    if not same_attempt or not isinstance(existing, dict):
        return incoming
    existing_snapshot_id = existing.get("snapshotId")
    incoming_snapshot_id = incoming.get("snapshotId")
    if existing_snapshot_id and incoming_snapshot_id and existing_snapshot_id != incoming_snapshot_id:
        return existing
    if existing_snapshot_id and not incoming_snapshot_id:
        return existing
    # A client race can produce two different analyses with the same attempt
    # counter. Only merge a result when its scored snapshot agrees with the
    # stored one; otherwise keep the first complete snapshot instead of
    # creating a hybrid from two recordings. Audio and self-evaluation fields
    # are intentionally outside this core set and may enrich that snapshot.
    for key in _RESULT_CORE_FIELDS:
        existing_value = existing.get(key)
        incoming_value = incoming.get(key)
        if (
            existing_value not in (None, "", [], {})
            and incoming_value not in (None, "", [], {})
            and existing_value != incoming_value
        ):
            return existing
    merged = dict(existing)
    for key, value in incoming.items():
        if value in (None, "", [], {}) and merged.get(key) not in (None, "", [], {}):
            continue
        merged[key] = value
    return merged


@router.get("/api/speaking-progress")
async def list_speaking_progress(
    topic_id: str,
    identity: auth.Identity = Depends(auth.require_student),
):
    with connect_db() as db:
        rows = db.execute(
            "SELECT * FROM speaking_progress WHERE student_id = %s AND topic_id = %s",
            (identity.id, topic_id),
        ).fetchall()
    return [row_to_speaking_progress(row) for row in rows]


@router.put("/api/speaking-progress")
async def upsert_speaking_progress(
    progress: SpeakingProgressRequest,
    identity: auth.Identity = Depends(auth.require_student),
):
    progress.studentId = identity.id
    row_id = f"{progress.studentId}:{progress.topicId}:{progress.sceneIndex}"
    latest_result = dict(progress.latestResult) if progress.latestResult is not None else None
    if progress.baseStoryId or progress.difficultyLevel or progress.promptId:
        if latest_result is not None:
            if progress.baseStoryId:
                latest_result["baseStoryId"] = progress.baseStoryId
            if progress.difficultyLevel:
                latest_result["difficultyLevel"] = progress.difficultyLevel
            latest_result["sceneIndex"] = progress.sceneIndex
            if progress.promptId:
                latest_result["promptId"] = progress.promptId
    with connect_db() as db:
        # The SELECT below cannot lock a row that does not exist yet. A
        # transaction-scoped advisory lock closes that first-insert race while
        # keeping the deterministic scene key as the lock identity.
        db.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (row_id,),
        )
        existing = db.execute(
            """
            SELECT attempts, best_tone, best_fluency, mastery_passed,
                   content_passed, cleared_words, latest_result
            FROM speaking_progress
            WHERE id = %s
            FOR UPDATE
            """,
            (row_id,),
        ).fetchone()

        if existing:
            merged_attempts = max(existing["attempts"], progress.attempts)
            merged_best_tone = max(existing["best_tone"], progress.bestTone)
            merged_best_fluency = max(existing["best_fluency"], progress.bestFluency)
            merged_mastery_passed = bool(existing["mastery_passed"] or progress.masteryPassed)
            merged_content_passed = bool(existing["content_passed"] or progress.contentPassed)
            if progress.attempts > existing["attempts"]:
                merged_cleared_words = _merge_cleared_words([], progress.clearedWords)
            elif progress.attempts == existing["attempts"]:
                merged_cleared_words = _merge_cleared_words(
                    existing["cleared_words"], progress.clearedWords
                )
            else:
                merged_cleared_words = _merge_cleared_words(existing["cleared_words"], [])
            # StoryRecorder increments attempts for each fresh analysis. A
            # stale request therefore has a lower attempt count and must not
            # replace the most recent feedback snapshot. Equal-count writes
            # remain valid for self-evaluation/audio-url enrichment.
            if latest_result is None:
                merged_latest_result = existing["latest_result"]
            elif progress.attempts < existing["attempts"]:
                merged_latest_result = existing["latest_result"]
            else:
                merged_latest_result = _merge_latest_result(
                    existing["latest_result"],
                    latest_result,
                    same_attempt=progress.attempts == existing["attempts"],
                )
        else:
            merged_attempts = progress.attempts
            merged_best_tone = progress.bestTone
            merged_best_fluency = progress.bestFluency
            merged_mastery_passed = progress.masteryPassed
            merged_content_passed = progress.contentPassed
            merged_cleared_words = _merge_cleared_words([], progress.clearedWords)
            merged_latest_result = latest_result

        db.execute(
            """
            INSERT INTO speaking_progress
                (id, student_id, topic_id, scene_index, attempts, best_tone,
                 best_fluency, mastery_passed, content_passed, cleared_words,
                 latest_result)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                attempts = GREATEST(speaking_progress.attempts, EXCLUDED.attempts),
                best_tone = GREATEST(speaking_progress.best_tone, EXCLUDED.best_tone),
                best_fluency = GREATEST(speaking_progress.best_fluency, EXCLUDED.best_fluency),
                mastery_passed = speaking_progress.mastery_passed OR EXCLUDED.mastery_passed,
                content_passed = speaking_progress.content_passed OR EXCLUDED.content_passed,
                cleared_words = EXCLUDED.cleared_words,
                latest_result = EXCLUDED.latest_result,
                updated_at = to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')
            """,
            (
                row_id,
                progress.studentId,
                progress.topicId,
                progress.sceneIndex,
                merged_attempts,
                merged_best_tone,
                merged_best_fluency,
                merged_mastery_passed,
                merged_content_passed,
                Jsonb(merged_cleared_words),
                Jsonb(merged_latest_result) if merged_latest_result is not None else None,
            ),
        )
    progress.attempts = merged_attempts
    progress.bestTone = merged_best_tone
    progress.bestFluency = merged_best_fluency
    progress.masteryPassed = merged_mastery_passed
    progress.contentPassed = merged_content_passed
    progress.clearedWords = merged_cleared_words
    progress.latestResult = merged_latest_result
    return progress
