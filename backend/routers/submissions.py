import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from psycopg.types.json import Jsonb

import auth
from database import connect_db, row_to_story_submission
from audio_concat import concatenate_scene_audio
from ai_feedback import generate_story_feedback
import main
from main import StorySubmissionRequest, SubmissionReviewRequest

router = APIRouter()


@router.get("/api/story-submissions")
def list_story_submissions(
    story_id: Optional[str] = None,
    student_id: Optional[str] = None,
    student_name: Optional[str] = None,
    include_scenes: bool = True,
    identity: auth.Identity = Depends(auth.get_current_identity),
):
    if identity.role == "student":
        student_id, student_name = identity.id, None

    conditions = []
    params: list[object] = []
    if story_id:
        conditions.append("story_id = %s")
        params.append(story_id)
    if student_id:
        conditions.append("student_id = %s")
        params.append(student_id)
    elif student_name:
        conditions.append("student_name = %s")
        params.append(student_name)
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""

    # The per-scene `scenes` JSONB (each scene's transcription, tone metrics and
    # audio) is the heavy part of a submission. The teacher dashboard's roster
    # and pending-count views read only the summary, so they can pass
    # include_scenes=false and skip it; the review view keeps the full payload.
    # Also replaces the endpoint's `SELECT *`.
    columns = (
        "id, story_id, story_title, student_name, student_id, submitted_at, "
        "concatenated_audio_url, story_feedback, review_status, teacher_note"
    )
    if include_scenes:
        columns += ", scenes"

    with connect_db() as db:
        rows = db.execute(
            f"SELECT {columns} FROM story_submissions{where} ORDER BY submitted_at DESC",
            params,
        ).fetchall()
    return [row_to_story_submission(row) for row in rows]


@router.patch("/api/story-submissions/{submission_id}/review")
def update_story_submission_review(
    submission_id: str,
    review: SubmissionReviewRequest,
    identity: auth.Identity = Depends(auth.require_teacher_or_admin),
):
    if review.status not in {"pending", "reviewed"}:
        raise HTTPException(
            status_code=400,
            detail="Review status must be pending or reviewed.",
        )

    with connect_db() as db:
        updated = db.execute(
            """
            UPDATE story_submissions
            SET review_status = %s, teacher_note = %s
            WHERE id = %s
            RETURNING *
            """,
            (review.status, review.note, submission_id),
        ).fetchone()
        if updated is None:
            raise HTTPException(status_code=404, detail="Story submission not found")
    return row_to_story_submission(updated)


@router.post("/api/story-submissions")
async def create_story_submission(
    submission: StorySubmissionRequest,
    identity: auth.Identity = Depends(auth.require_student),
):
    submission.studentId = identity.id
    scenes_sorted = sorted(submission.scenes, key=lambda s: s.sceneIndex)

    with connect_db() as db:
        existing = db.execute(
            "SELECT student_id FROM story_submissions WHERE id = %s",
            (submission.id,),
        ).fetchone()
        if existing is not None and existing.get("student_id") != identity.id:
            raise HTTPException(
                status_code=409,
                detail="Submission already belongs to another student.",
            )
        db.execute(
            """
            INSERT INTO story_submissions
                (id, story_id, story_title, student_name, student_id, submitted_at, scenes)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                story_id = EXCLUDED.story_id,
                story_title = EXCLUDED.story_title,
                student_name = EXCLUDED.student_name,
                student_id = EXCLUDED.student_id,
                submitted_at = EXCLUDED.submitted_at,
                scenes = EXCLUDED.scenes
            """,
            (
                submission.id,
                submission.storyId,
                submission.storyTitle,
                submission.studentName,
                submission.studentId,
                submission.submittedAt,
                Jsonb([s.model_dump() for s in scenes_sorted]),
            ),
        )

    # Story-level concatenated audio + holistic feedback are best-effort: the
    # scenes above are already durably saved, so a failure here must never
    # fail the whole submission — the student just doesn't get the story-level
    # extras this time (no retry, per the synchronous/no-background-job design).
    concatenated_audio_url: Optional[str] = None
    try:
        story_audio_path = os.path.join(
            main.STORY_AUDIO_UPLOAD_DIR, f"{main.safe_file_stem(submission.id)}.wav"
        )
        wrote_file = concatenate_scene_audio(
            [s.audioUrl for s in scenes_sorted if s.audioUrl],
            upload_dir=main.UPLOAD_DIR,
            output_path=story_audio_path,
        )
        if wrote_file:
            concatenated_audio_url = f"/uploads/story_audio/{os.path.basename(story_audio_path)}"
    except Exception as exc:
        main.logger.error("Story audio concatenation failed for %s: %s", submission.id, exc)

    story_feedback: Optional[dict] = None
    try:
        # Keep every scene in the transcript, even ones the ASR came back empty
        # for (silence, recognition miss) — dropping them would silently shrink
        # a 3-scene story down to whatever subset had text, so the "whole story"
        # feedback would really only be judging part of it.
        combined_transcript = "\n".join(
            f"[Scene {s.sceneIndex + 1}] {s.transcription.strip() or '(no speech transcribed for this scene)'}"
            for s in scenes_sorted
        )
        has_any_speech = any(s.transcription.strip() for s in scenes_sorted)
        if has_any_speech:
            # Average the per-scene Praat metrics already computed during
            # recording (tone accuracy, fluency, word-prosody/pronunciation)
            # across the whole story, so the story-level Fluency-and-Coherence
            # and Pronunciation dimensions are grounded in real acoustic data
            # instead of a text-only guess. Scenes with no speech contribute a
            # real 0, which correctly drags the average down for a genuine gap.
            scene_count = len(scenes_sorted) or 1
            avg_tone_accuracy = sum(s.toneAccuracy for s in scenes_sorted) / scene_count
            avg_fluency_score = sum(s.fluencyScore for s in scenes_sorted) / scene_count
            avg_pron_score = sum(s.pronScore for s in scenes_sorted) / scene_count
            # Real delivery data (not just the composite fluency score) so the
            # story-level feedback can cite actual pausing/utterance behavior —
            # this matters more now that a scene can hand the student a
            # suggestedAnswer to read, where vocabulary/grammar isn't really a
            # choice the student is making, but delivery still is.
            total_pause_count = sum(s.pauseCount for s in scenes_sorted)
            longest_single_pause = max((s.longestPause for s in scenes_sorted), default=0)
            total_utterance_count = sum(s.utteranceCount for s in scenes_sorted)
            total_choppy_pause_count = sum(s.choppyPauseCount for s in scenes_sorted)
            avg_articulation_rate = sum(s.articulationRate for s in scenes_sorted) / scene_count
            story_feedback = await generate_story_feedback(
                combined_transcript,
                avg_tone_accuracy=avg_tone_accuracy,
                avg_fluency_score=avg_fluency_score,
                avg_pron_score=avg_pron_score,
                total_pause_count=total_pause_count,
                longest_single_pause=longest_single_pause,
                total_utterance_count=total_utterance_count,
                scene_count=scene_count,
                total_choppy_pause_count=total_choppy_pause_count,
                avg_articulation_rate=avg_articulation_rate,
            )
    except Exception as exc:
        main.logger.error("Story feedback generation failed for %s: %s", submission.id, exc)

    with connect_db() as db:
        updated = db.execute(
            """
            UPDATE story_submissions
            SET concatenated_audio_url = %s, story_feedback = %s
            WHERE id = %s
            RETURNING *
            """,
            (
                concatenated_audio_url,
                Jsonb(story_feedback) if story_feedback else None,
                submission.id,
            ),
        ).fetchone()

    return row_to_story_submission(updated)
