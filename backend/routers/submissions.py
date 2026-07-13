import json
import os
from typing import Optional

from fastapi import APIRouter

from database import connect_db, row_to_story_submission
from audio_concat import concatenate_scene_audio
from ai_feedback import generate_story_feedback
import main
from main import StorySubmissionRequest

router = APIRouter()


@router.get("/api/story-submissions")
async def list_story_submissions(story_id: Optional[str] = None):
    with connect_db() as db:
        if story_id:
            rows = db.execute(
                "SELECT * FROM story_submissions WHERE story_id = ? ORDER BY submitted_at DESC",
                (story_id,),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM story_submissions ORDER BY submitted_at DESC"
            ).fetchall()
    return [row_to_story_submission(row) for row in rows]


@router.post("/api/story-submissions")
async def create_story_submission(submission: StorySubmissionRequest):
    scenes_sorted = sorted(submission.scenes, key=lambda s: s.sceneIndex)

    with connect_db() as db:
        db.execute(
            """
            INSERT OR REPLACE INTO story_submissions
                (id, story_id, story_title, student_name, submitted_at, scenes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                submission.id,
                submission.storyId,
                submission.storyTitle,
                submission.studentName,
                submission.submittedAt,
                json.dumps([s.model_dump() for s in scenes_sorted]),
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
            story_feedback = await generate_story_feedback(
                combined_transcript,
                avg_tone_accuracy=avg_tone_accuracy,
                avg_fluency_score=avg_fluency_score,
                avg_pron_score=avg_pron_score,
                total_pause_count=total_pause_count,
                longest_single_pause=longest_single_pause,
                total_utterance_count=total_utterance_count,
                scene_count=scene_count,
            )
    except Exception as exc:
        main.logger.error("Story feedback generation failed for %s: %s", submission.id, exc)

    with connect_db() as db:
        db.execute(
            "UPDATE story_submissions SET concatenated_audio_url = ?, story_feedback = ? WHERE id = ?",
            (
                concatenated_audio_url,
                json.dumps(story_feedback) if story_feedback else None,
                submission.id,
            ),
        )

    return {
        **submission.model_dump(),
        "scenes": [s.model_dump() for s in scenes_sorted],
        "concatenatedAudioUrl": concatenated_audio_url,
        "storyFeedback": story_feedback,
    }
