"""Uvicorn entrypoint: build the app, wire lifespan + routers, run it.

Re-exports a handful of names other modules still reach through `main`
directly: routers/verified_speaking.py's lazy _main_module() test-stub seam,
tests that patch/call things on `main`, and the two upload-dir constants
routers/submissions.py reads. Everything else imports the real module it
needs directly.

The `models` re-export block is the bulk of why this file is over the
project's ~40-line main.py target for now: many routers still do
`from main import SomeRequest` instead of `from models import SomeRequest`.
Splitting models.py by domain and updating those imports is separate,
later work - not done here to keep this structural move (main_parts ->
application/) isolated and easy to verify on its own.
"""

from __future__ import annotations

from typing import Optional

from application.logging_config import configure_logging

logger = configure_logging()

# Re-exported for routers/verified_speaking.py's test-stub seam and tests
# that patch/call these directly on `main`.
from services.media import (
    resolve_media_b64,
    save_uploaded_audio,
    save_verified_audio_record,
    remove_uploaded_file,
    UPLOAD_DIR,
    STORY_AUDIO_UPLOAD_DIR,
)
from services.content_verification import _MAX_AUDIO_BYTES
from services.speech_analysis import _do_analyze
from application.analysis_capacity import (
    acquire_analysis_slot,
    ANALYZE_TIMEOUT_SECONDS,
    ANALYZE_CONCURRENCY_LIMIT,
    ANALYZE_QUEUE_LIMIT,
    analyze_semaphore,
)
from application.middleware import _check_rate_limit
# Pure data models, re-exported bare so every existing `from main import X`
# router/test import keeps working unchanged.
from api.schemas.models import (
    SpeakingProgressRequest,
    CustomStoryFrameRequest,
    CustomStoryRequest,
    HelpRequest,
    SceneSubmission,
    StorySubmissionRequest,
    SubmissionReviewRequest,
    VocabQuizQuestionResult,
    VocabQuizAttemptRequest,
    StudentCreateRequest,
    StudentPasswordResetRequest,
    StudentUpdateRequest,
    QuizExclusion,
    QuizExclusionsUpdateRequest,
    QuizClozeCandidateIn,
    QuizSynonymCandidateIn,
    QuizWordMaterialIn,
    QuizApproveRequest,
    QuizPendingApprovalsUpdateRequest,
    QuizQuestionReplaceRequest,
    StudentLoginRequest,
    Student,
    TeacherCreateRequest,
    TeacherLoginRequest,
    TeacherUpdateRequest,
    MAX_VOCAB_DISTRACTORS_PER_WORD,
    VocabularyDistractorsUpdateRequest,
    MAX_VOCAB_CLOZE_PER_WORD,
    VocabularyClozeUpdateRequest,
    MAX_VOCAB_SYNONYM_PER_WORD,
    VocabularySynonymUpdateRequest,
    TTSRequest,
    RecordingQualityMetrics,
    FeedbackQuality,
    ProcessingTraceStage,
    ProcessingTrace,
    ContentDiffSegment,
    AnalysisResponse,
)


def clean_api_key(value: Optional[str]) -> Optional[str]:
    key = (value or "").strip()
    if not key or "your_" in key.lower() or key.lower().endswith("_here"):
        return None
    return key


from application.app_factory import create_app

app = create_app()

from application.lifespan import register_lifespan_handlers

register_lifespan_handlers(app)

# Imported only now: each router does `from main import X` / `import main`
# at its own module level, and needs the names above already bound.
from application.router_registry import register_routers

register_routers(app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
