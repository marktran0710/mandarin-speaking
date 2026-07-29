from psycopg.types.json import Jsonb

from database import connect_db, row_to_speaking_progress
from main import SpeakingProgressRequest
from fastapi import APIRouter

router = APIRouter()


@router.get("/api/speaking-progress")
async def list_speaking_progress(student_id: str, topic_id: str):
    with connect_db() as db:
        rows = db.execute(
            "SELECT * FROM speaking_progress WHERE student_id = %s AND topic_id = %s",
            (student_id, topic_id),
        ).fetchall()
    return [row_to_speaking_progress(row) for row in rows]


@router.put("/api/speaking-progress")
async def upsert_speaking_progress(progress: SpeakingProgressRequest):
    row_id = f"{progress.studentId}:{progress.topicId}:{progress.sceneIndex}"
    with connect_db() as db:
        db.execute(
            """
            INSERT INTO speaking_progress
                (id, student_id, topic_id, scene_index, attempts, best_tone,
                 best_fluency, mastery_passed, content_passed, cleared_words)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                attempts = EXCLUDED.attempts,
                best_tone = EXCLUDED.best_tone,
                best_fluency = EXCLUDED.best_fluency,
                mastery_passed = EXCLUDED.mastery_passed,
                content_passed = EXCLUDED.content_passed,
                cleared_words = EXCLUDED.cleared_words,
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
            ),
        )
    return progress
