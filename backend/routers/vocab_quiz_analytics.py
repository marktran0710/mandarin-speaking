from fastapi import APIRouter, Depends

import security.auth as auth
import services.vocab_quiz_analytics_service as vocab_quiz_analytics_service
from db import connect_db


router = APIRouter()


@router.get("/api/analytics/vocab-quiz/frex")
def get_vocab_quiz_frex(
    top: int = 5,
    identity: auth.Identity = Depends(auth.get_current_identity),
):
    """Return characteristic missed words grouped by student."""
    with connect_db() as db:
        return vocab_quiz_analytics_service.get_frex(db, top)
