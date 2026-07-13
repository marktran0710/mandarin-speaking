from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from database import connect_db, row_to_audio_record
import main
from main import AudioRecordRequest

router = APIRouter()


@router.get("/api/audio-records")
async def list_audio_records(
    limit: int = Query(default=200, ge=1, le=1000),
    skip: int = Query(default=0, ge=0),
):
    with connect_db() as db:
        rows = db.execute(
            "SELECT * FROM audio_records ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, skip),
        ).fetchall()
    return [row_to_audio_record(row) for row in rows]


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
    main.save_audio_record(audio_record)
    return audio_record


@router.delete("/api/audio-records/{record_id}")
async def delete_audio_record(record_id: str):
    with connect_db() as db:
        row = db.execute(
            "SELECT audio_url FROM audio_records WHERE id = ?",
            (record_id,),
        ).fetchone()
        db.execute("DELETE FROM audio_records WHERE id = ?", (record_id,))
    if row and row["audio_url"]:
        main.remove_uploaded_file(row["audio_url"])
    return {"ok": True}
