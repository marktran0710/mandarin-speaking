from fastapi import APIRouter, Depends

import security.auth as auth
from services.learning_engine_service import get_learning_engine_metadata

router = APIRouter()


@router.get("/api/admin/learning-engine")
def get_learning_engine(identity: auth.Identity = Depends(auth.require_admin)):
    """Runtime BKT/retention/voice-scoring metadata for the admin Learning Engine page.

    Everything returned here is read live from the modules that actually
    control production behavior - see services/learning_engine_service.py.
    """
    return get_learning_engine_metadata()
