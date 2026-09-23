from fastapi import APIRouter, Depends, HTTPException

import security.auth as auth
import services.quiz_review_service as quiz_review_service
from main import QuizApproveRequest

router = APIRouter(dependencies=[Depends(auth.require_teacher_or_admin)])


@router.post("/api/custom-stories/{story_id}/quiz/approve")
async def approve_quiz_material(story_id: str, request: QuizApproveRequest):
    try:
        return quiz_review_service.approve_quiz_material(
            story_id, request.level, [w.model_dump() for w in request.material]
        )
    except quiz_review_service.QuizReviewError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
