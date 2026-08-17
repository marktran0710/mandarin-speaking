from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from database import connect_db, row_to_audio_record
import main
from main import AudioRecordRequest

router = APIRouter()


@router.get("/api/audio-records")
async def list_audio_records(
    limit: int = Query(default=200, ge=1, le=1000),
    skip: int = Query(default=0, ge=0),
    student_id: Optional[str] = Query(default=None),
    topic_id: Optional[str] = Query(default=None),
):
    query = "SELECT * FROM audio_records"
    params: list[object] = []
    filters: list[str] = []
    if student_id:
        filters.append("student_id = %s")
        params.append(student_id)
    if topic_id:
        filters.append("topic_id = %s")
        params.append(topic_id)
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s"
    params.extend([limit, skip])
    with connect_db() as db:
        rows = db.execute(query, params).fetchall()
    return [row_to_audio_record(row) for row in rows]


@router.get("/api/audio-records/latest-by-scene")
async def list_latest_audio_records_by_scene(
    student_id: str = Query(...),
    topic_id: str = Query(...),
):
    """One row per scene (image_index): whichever attempt is newest, so a
    student reopening a story sees the practice result they left off with
    instead of a blank slate — `audio_records` itself is an append-only log
    of every attempt with no such "latest" concept on its own."""
    query = """
        SELECT DISTINCT ON (image_index) *
        FROM audio_records
        WHERE student_id = %s AND topic_id = %s
        ORDER BY image_index, created_at DESC, id DESC
    """
    with connect_db() as db:
        rows = db.execute(query, (student_id, topic_id)).fetchall()
    return [row_to_audio_record(row) for row in rows]


@router.get("/api/audio-records/count")
async def get_audio_record_count():
    with connect_db() as db:
        total = db.execute("SELECT COUNT(*) AS total FROM audio_records").fetchone()["total"]
    return {"total": total}


@router.post("/api/audio-records")
async def create_audio_record(record: AudioRecordRequest):
    main.save_audio_record(record)
    return record


@router.post("/api/audio-records/upload")
async def upload_audio_record(
    record: str = Form(...),
    file: UploadFile = File(...),
):
    try:
        audio_record = AudioRecordRequest.model_validate_json(record)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid audio record JSON") from exc

    audio_record.audioUrl = await main.save_uploaded_audio(file, audio_record.id)
    audio_record.audioName = audio_record.audioUrl.rsplit("/", 1)[-1]
    main.save_audio_record(audio_record)
    return audio_record


@router.delete("/api/audio-records/{record_id}")
async def delete_audio_record(record_id: str):
    with connect_db() as db:
        row = db.execute(
            "DELETE FROM audio_records WHERE id = %s RETURNING audio_url",
            (record_id,),
        ).fetchone()
    if row and row["audio_url"]:
        main.remove_uploaded_file(row["audio_url"])
    return {"ok": True}
