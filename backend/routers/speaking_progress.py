from psycopg.types.json import Jsonb

import auth
from database import connect_db, row_to_speaking_progress
from main import SpeakingProgressRequest
from fastapi import APIRouter, Depends

router = APIRouter()


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
    with connect_db() as db:
        db.execute(
            """
            INSERT INTO speaking_progress
                (id, student_id, topic_id, scene_index, attempts, best_tone,
                 best_fluency, mastery_passed, content_passed, cleared_words,
                 latest_result)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                attempts = EXCLUDED.attempts,
                best_tone = EXCLUDED.best_tone,
                best_fluency = EXCLUDED.best_fluency,
                mastery_passed = EXCLUDED.mastery_passed,
                content_passed = EXCLUDED.content_passed,
                cleared_words = EXCLUDED.cleared_words,
                latest_result = EXCLUDED.latest_result,
                updated_at = to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')
            """,
            (
                row_id,
                progress.studentId,
                progress.topicId,
                progress.sceneIndex,
                progress.attempts,
                progress.bestTone,
                progress.bestFluency,
                progress.masteryPassed,
                progress.contentPassed,
                Jsonb(progress.clearedWords),
                Jsonb(progress.latestResult) if progress.latestResult is not None else None,
            ),
        )
    return progress
