"""Use-case orchestration for story submissions: listing, teacher review,
and the create flow (scene persistence, best-effort audio concatenation, and
best-effort story-level feedback generation).

Coordinates the submission repository with the audio-concat helper and the
AI feedback service. Raises SubmissionServiceError (not HTTPException) - the
router maps it to an HTTP status code.

The create flow is deliberately split into three functions (rather than one,
as the rest of this codebase's services prefer) because the original router
opened *two separate* ``connect_db()`` transactions around it: the scene
write commits and becomes durable/visible to other readers before the
best-effort audio-concat and AI-feedback-generation work runs (which can
take a real amount of wall-clock time via the LLM call), and only the
final extras update opens a second transaction. Collapsing that into one
connection would hold the scenes uncommitted for the whole best-effort
window, changing observable behavior for any concurrent reader - so the
router still opens two ``connect_db()`` blocks for this endpoint, exactly as
before.
"""
import os
from typing import Optional

import main
import services.media as media_service
from helpers.audio_concat import concatenate_scene_audio
from repositories import submission_repository as repo
from repositories.database import row_to_story_submission
from services.ai_feedback import generate_story_feedback


class SubmissionServiceError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def list_story_submissions(
    db,
    *,
    role: str,
    story_id: Optional[str],
    student_id: Optional[str],
    student_name: Optional[str],
    include_scenes: bool,
) -> list[dict]:
    rows = repo.find_submissions(
        db,
        exclude_test_accounts=role == "teacher",
        story_id=story_id,
        student_id=student_id,
        student_name=student_name,
        include_scenes=include_scenes,
    )
    return [row_to_story_submission(row) for row in rows]


def update_story_submission_review(db, submission_id: str, status: str, note) -> dict:
    if status not in {"pending", "reviewed"}:
        raise SubmissionServiceError(400, "Review status must be pending or reviewed.")
    updated = repo.update_review(db, submission_id, status, note)
    if updated is None:
        raise SubmissionServiceError(404, "Story submission not found")
    return row_to_story_submission(updated)


def persist_submission_scenes(db, submission) -> list:
    """Ownership-check and durably upsert the scene list. Returns the
    scenes sorted by sceneIndex, as the caller needs that ordering for the
    best-effort audio-concat/feedback step that follows.
    """
    scenes_sorted = sorted(submission.scenes, key=lambda s: s.sceneIndex)

    existing = repo.find_owner(db, submission.id)
    if existing is not None and existing.get("student_id") != submission.studentId:
        raise SubmissionServiceError(409, "Submission already belongs to another student.")
    repo.upsert_scenes(
        db,
        id=submission.id,
        story_id=submission.storyId,
        story_title=submission.storyTitle,
        student_name=submission.studentName,
        student_id=submission.studentId,
        submitted_at=submission.submittedAt,
        scenes=[s.model_dump() for s in scenes_sorted],
    )
    return scenes_sorted


async def build_story_extras(submission_id: str, scenes_sorted: list) -> tuple:
    """Best-effort story-level concatenated audio + AI feedback. Never
    raises - a failure here must never fail the whole submission, since the
    scenes are already durably saved by the time this runs.
    """
    concatenated_audio_url: Optional[str] = None
    try:
        story_audio_path = os.path.join(
            main.STORY_AUDIO_UPLOAD_DIR, f"{media_service.safe_file_stem(submission_id)}.wav"
        )
        wrote_file = concatenate_scene_audio(
            [s.audioUrl for s in scenes_sorted if s.audioUrl],
            upload_dir=main.UPLOAD_DIR,
            output_path=story_audio_path,
        )
        if wrote_file:
            concatenated_audio_url = f"/uploads/story_audio/{os.path.basename(story_audio_path)}"
    except Exception as exc:
        main.logger.error("Story audio concatenation failed for %s: %s", submission_id, exc)

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
        main.logger.error("Story feedback generation failed for %s: %s", submission_id, exc)

    return concatenated_audio_url, story_feedback


def finalize_story_submission(
    db, submission_id: str, concatenated_audio_url: Optional[str], story_feedback: Optional[dict]
) -> dict:
    updated = repo.update_story_extras(db, submission_id, concatenated_audio_url, story_feedback)
    return row_to_story_submission(updated)
