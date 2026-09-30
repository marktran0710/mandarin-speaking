"""Read-only export of teacher model contours + real learner attempts to JSON."""
import json

import db

out = {"teacher": [], "attempts": []}
with db.connect_db() as conn:
    stories = {}
    for row in conn.execute("SELECT id, frames FROM custom_stories").fetchall():
        for i, frame in enumerate(row["frames"] or []):
            raw = frame.get("sentenceModelContour")
            if not raw:
                continue
            try:
                contour = json.loads(raw)
            except Exception:
                continue
            stories[(row["id"], i)] = contour
            out["teacher"].append({"story": row["id"], "frame": i, "contour": contour})
    records = conn.execute(
        "SELECT id, topic_id, image_index, student_id, praat_metrics FROM audio_records "
        "WHERE praat_metrics IS NOT NULL AND jsonb_typeof(praat_metrics->'word_prosody') = 'array'"
    ).fetchall()
    for rec in records:
        story = str(rec["topic_id"]).removeprefix("teacher-")
        contour = stories.get((story, rec["image_index"]))
        if not contour:
            continue
        pm = rec["praat_metrics"]
        out["attempts"].append({
            "id": rec["id"], "student": rec["student_id"], "story": story, "frame": rec["image_index"],
            "transcript": pm.get("transcription") or pm.get("recognized_text") or "",
            "pitchContour": pm.get("pitch_contour") or [],
            "words": [
                {k: w.get(k) for k in ("token", "index", "start_time", "end_time", "reference_source", "shape_score", "expected_tones")}
                for w in pm["word_prosody"]
            ],
        })
json.dump(out, open("/tmp/export.json", "w", encoding="utf-8"), ensure_ascii=False)
print("teacher frames", len(out["teacher"]), "attempts", len(out["attempts"]))
