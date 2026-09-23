from fastapi import APIRouter, Depends

import security.auth as auth
import services.story_quiz_materials_service as story_quiz_materials_service
from db import connect_db
from api.schemas.models import (
    QuizExclusionsUpdateRequest,
    QuizPendingApprovalsUpdateRequest,
    QuizQuestionReplaceRequest,
)


router = APIRouter(dependencies=[Depends(auth.require_story_access)])


@router.put("/api/custom-stories/{story_id}/quiz-exclusions")
def update_quiz_exclusions(story_id: str, request: QuizExclusionsUpdateRequest):
    with connect_db() as db:
        return story_quiz_materials_service.update_quiz_exclusions(db, story_id, request)


@router.put("/api/custom-stories/{story_id}/quiz-pending-approvals")
def update_quiz_pending_approvals(story_id: str, request: QuizPendingApprovalsUpdateRequest):
    with connect_db() as db:
        return story_quiz_materials_service.update_quiz_pending_approvals(db, story_id, request)


@router.put("/api/custom-stories/{story_id}/quiz-question")
def replace_quiz_question(story_id: str, request: QuizQuestionReplaceRequest):
    with connect_db() as db:
        return story_quiz_materials_service.replace_quiz_question(db, story_id, request)
