from fastapi import APIRouter, Depends, Query

import security.auth as auth
from db import connect_db
from routers.vocab_quiz_mastery import _assert_student_scope
from services.vocab_quiz_progression_service import get_progression


router = APIRouter()


@router.get("/api/students/{student_id}/vocabulary-progression")
def get_student_vocabulary_progression(
    student_id: str,
    story_id: str = Query(...),
    identity: auth.Identity = Depends(auth.get_current_identity),
):
    _assert_student_scope(identity, student_id)
    with connect_db() as db:
        return get_progression(db, student_id, story_id)
