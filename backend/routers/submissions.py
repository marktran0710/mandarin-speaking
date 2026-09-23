from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

import security.auth as auth
import services.submission_service as submission_service
from db import connect_db
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

    with connect_db() as db:
        return submission_service.list_story_submissions(
            db,
            role=identity.role,
            story_id=story_id,
            student_id=student_id,
            student_name=student_name,
            include_scenes=include_scenes,
        )


@router.patch("/api/story-submissions/{submission_id}/review")
def update_story_submission_review(
    submission_id: str,
    review: SubmissionReviewRequest,
    identity: auth.Identity = Depends(auth.require_teacher_or_admin),
):
    with connect_db() as db:
        try:
            return submission_service.update_story_submission_review(
                db, submission_id, review.status, review.note
            )
        except submission_service.SubmissionServiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/api/story-submissions")
async def create_story_submission(
    submission: StorySubmissionRequest,
    identity: auth.Identity = Depends(auth.require_student),
):
    submission.studentId = identity.id

    with connect_db() as db:
        try:
            scenes_sorted = submission_service.persist_submission_scenes(db, submission)
        except submission_service.SubmissionServiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    concatenated_audio_url, story_feedback = await submission_service.build_story_extras(
        submission.id, scenes_sorted
    )

    with connect_db() as db:
        return submission_service.finalize_story_submission(
            db, submission.id, concatenated_audio_url, story_feedback
        )
