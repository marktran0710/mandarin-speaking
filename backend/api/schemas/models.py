"""Pydantic request/response models shared across routers.

Pure data shapes, no business logic ??kept separate from services/ (which
does have logic) and from routers/ (which own the endpoints that validate
against these models).
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field


class ConversationTurnRequest(BaseModel):
    id: str = Field(..., min_length=1, max_length=128)
    speaker: Literal["system", "student"]
    text: str = Field(..., min_length=1, max_length=4000)
    # SYSTEM turn: audio the learner listens to as the conversation partner.
    # No max_length - like frames' listenAudioUrl, this carries a base64
    # data: URL at save time (persist_story_conversation_audio converts it
    # to a short /uploads/ URL before it's ever stored), not just a URL.
    audioUrl: Optional[str] = None
    # STUDENT turn: the expected response, plus an optional model recording
    # of it - never the same thing as audioUrl above (the character's line).
    targetText: Optional[str] = Field(default=None, max_length=4000)
    targetAudioUrl: Optional[str] = None
    pinyin: Optional[str] = Field(default=None, max_length=4000)
    translation: Optional[str] = Field(default=None, max_length=4000)


class SpeakingProgressRequest(BaseModel):
    studentId: str
    topicId: str
    sceneIndex: int = Field(..., ge=0)
    attempts: int = Field(default=0, ge=0)
    bestTone: float = Field(default=0, ge=0, le=100)
    bestFluency: float = Field(default=0, ge=0, le=100)
    masteryPassed: bool = False
    contentPassed: bool = False
    clearedWords: List[str] = Field(default_factory=list)
    # The latest accepted per-scene submission snapshot. Kept nullable so
    # rows written before this field was introduced remain fully compatible.
    latestResult: Optional[Dict[str, Any]] = None
    # Additive story/prompt identity. The existing latest_result JSONB stores
    # these fields, so no speaking-progress table migration is required.
    baseStoryId: Optional[str] = Field(default=None, max_length=128)
    difficultyLevel: Optional[str] = None  # round key (tier1/2/3) or legacy label; server resolver is authoritative
    promptId: Optional[str] = Field(default=None, max_length=200)
    # A link is eligible only when the server validates this immutable audio
    # record; legacy request values remain supported for history round-trips.
    verifiedAudioRecordId: Optional[str] = Field(default=None, max_length=128)
    progressionEligible: bool = False
    conversationId: Optional[str] = Field(default=None, max_length=200)
    turnId: Optional[str] = Field(default=None, max_length=128)
    turnIndex: Optional[int] = Field(default=None, ge=0)


class CustomStoryFrameRequest(BaseModel):
    imageUrl: str
    prompt: str
    vocabulary: str = ""
    vocabularyGroups: Optional[List[dict]] = None
    grammarPattern: Optional[str] = None
    grammarExample: Optional[str] = None
    vocabularyPinyin: Optional[str] = None
    vocabularyPos: Optional[str] = None
    vocabularyTranslation: Optional[str] = None
    phrases: Optional[str] = None
    phrasesTranslation: Optional[str] = None
    suggestedAnswer: Optional[str] = None
    listenAudioUrl: Optional[str] = None
    listenAudioSource: Optional[Literal["teacher"]] = None
    listenScript: Optional[str] = None
    vocabularyAudioUrls: Optional[str] = None
    vocabularyReferenceCurves: Optional[str] = None
    sentenceReferenceCurves: Optional[str] = None

    vocabularyAudioUrlsMedium: Optional[str] = None
    vocabularyAudioUrlsHard: Optional[str] = None
    vocabularyReferenceCurvesMedium: Optional[str] = None
    vocabularyReferenceCurvesHard: Optional[str] = None
    sentenceReferenceCurvesMedium: Optional[str] = None
    sentenceReferenceCurvesHard: Optional[str] = None


class CustomStoryRequest(BaseModel):
    id: str
    title: str
    frames: List[CustomStoryFrameRequest]
    conversationTurns: Optional[List[ConversationTurnRequest]] = None
    # Canonical vocabulary and reusable phrases for the complete story, keyed
    # by level. These remain optional so stories authored before story-level
    # learning content was introduced can still be read and re-saved unchanged.
    storyVocabulary: Optional[Dict[str, Dict[str, str]]] = None
    storyPhrases: Optional[Dict[str, Dict[str, str]]] = None
    # Validated, stable CSV question bank. Each word has one observation per
    # round; the backend stores it separately from frame text.
    vocabAssessment: Optional[List[Dict[str, Any]]] = None
    published: bool = False
    lessonNumber: Optional[int] = None
    lessonSubOrder: Optional[int] = None
    rubricScores: Optional[Dict[str, Any]] = None


class HelpRequest(BaseModel):
    id: str = Field(..., max_length=128)
    studentName: str = Field(default="Student", max_length=100)
    message: str = Field(default="I need teacher help.", max_length=500)
    status: str = "open"
    createdAt: str
    resolvedAt: Optional[str] = None


class SceneSubmission(BaseModel):
    sceneIndex: int
    # Canonical story/tier identity is stored with every scene so a returned
    # submission can rehydrate difficulty progression after a reload. Older
    # submissions intentionally remain valid without these optional fields.
    baseStoryId: Optional[str] = Field(default=None, max_length=128)
    difficultyLevel: Optional[str] = None  # round key (tier1/2/3) or legacy label; server resolver is authoritative
    imageUrl: str = ""
    transcription: str = ""
    vocabUsed: List[str] = []
    vocabMissing: List[str] = []
    vocabScore: float = 0
    toneAccuracy: float = 0
    pronScore: float = 0
    fluencyScore: float = 0
    audioUrl: Optional[str] = None
    # Praat pause-analysis data for this scene's recording ??see
    # services.ai_feedback.generate_story_feedback for why this now feeds story-level
    # feedback directly (delivery matters more once scenes can hand the
    # student a suggestedAnswer to read, since vocab/grammar aren't a choice).
    pauseCount: float = 0
    longestPause: float = 0
    utteranceCount: float = 0
    # Judged pause placement + articulation rate ??see caf_metrics.classify_pauses
    # and caf_metrics.speech_rate_verdict for how these are derived.
    choppyPauseCount: float = 0
    articulationRate: float = 0
    # The student's own self-rating for this scene's accepted attempt, taken
    # right after they listened back to it and before seeing the system's
    # verdict. Absent when the student skipped the prompt.
    selfEvalContent: Optional[Literal["good", "ok", "bad"]] = None
    selfEvalPronunciation: Optional[Literal["good", "ok", "bad"]] = None


class StorySubmissionRequest(BaseModel):
    id: str = Field(..., max_length=128)
    storyId: str = Field(..., max_length=128)
    storyTitle: str = Field(default="", max_length=200)
    studentName: str = Field(default="Student", max_length=100)
    studentId: Optional[str] = Field(default=None, max_length=128)
    submittedAt: str
    scenes: List[SceneSubmission] = []


class SubmissionReviewRequest(BaseModel):
    status: str
    note: Optional[str] = None


class VocabQuizQuestionResult(BaseModel):
    word: str = Field(..., max_length=200)
    correct: bool
    timeMs: int = Field(..., ge=0)
    # Optional item identity metadata. Legacy rows only have word/correct/timeMs
    # and continue to be accepted by the same JSONB endpoint.
    itemId: Optional[str] = Field(default=None, max_length=256)
    conceptId: Optional[str] = Field(default=None, max_length=200)
    questionKind: Optional[str] = Field(default=None, max_length=40)
    round: Optional[Literal[1, 2, 3]] = None
    tier: Optional[Literal["tier1", "tier2", "tier3"]] = None
    # Legacy read compatibility only. New clients send numeric round/tier.
    roundType: Optional[Literal["know_it", "say_it", "use_it"]] = None
    knowledgeDimension: Optional[Literal["meaning", "pinyin_production", "contextual_recall"]] = None
    activityType: Optional[Literal["diagnostic", "personalized_practice", "scheduled_maintenance", "challenge", "practice"]] = None
    level: Optional[str] = None  # legacy attempt metadata; server resolver is authoritative
    baseStoryId: Optional[str] = Field(default=None, max_length=128)
    itemVersion: Optional[str] = Field(default=None, max_length=40)
    # Server-side BKT gate metadata.  These are deliberately optional for
    # legacy attempts: old responses remain readable but are never treated as
    # clean diagnostic evidence by the strict analytics path.
    isBktEligible: Optional[bool] = None
    bktEligibilityErrors: List[str] = []
    diagnosticExposureId: Optional[str] = Field(default=None, max_length=256)
    assistedResponse: bool = False
    bktValidationStatus: Optional[Literal["APPROVED", "DRAFT"]] = None
    lessonId: Optional[str] = Field(default=None, max_length=128)
    quizId: Optional[str] = Field(default=None, max_length=128)
    selectedAnswer: Optional[str] = Field(default=None, max_length=500)
    correctAnswer: Optional[str] = Field(default=None, max_length=500)
    presentedOptions: List[str] = Field(default_factory=list)
    questionPrompt: Optional[str] = Field(default=None, max_length=2000)
    answeredAt: Optional[str] = None
    questionIndex: Optional[int] = Field(default=None, ge=0)


class VocabQuizAttemptRequest(BaseModel):
    id: str = Field(..., max_length=128)
    storyId: str = Field(..., max_length=128)
    studentName: str = Field(default="Student", max_length=100)
    studentId: Optional[str] = Field(default=None, max_length=128)
    mode: Optional[str] = None
    baseStoryId: Optional[str] = Field(default=None, max_length=128)
    level: Optional[str] = None  # round key (tier1/2/3) or legacy label; server resolver is authoritative
    completedAt: str
    totalQuestions: int = Field(..., ge=1)
    correctCount: int = Field(..., ge=0)
    totalTimeMs: int = Field(..., ge=0)
    questionResults: List[VocabQuizQuestionResult] = []


class ResearchProbeResponseRequest(BaseModel):
    # Never submitted through VocabQuizAttemptRequest/the quiz-attempt API
    # (Epic 7, Task 7.5) - a probe is a read-only measurement, not a graded
    # quiz round, so it gets its own minimal request shape.
    response: str = Field(..., max_length=2000)
    sourceResponseId: str = Field(..., max_length=128)


class StudentCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=6, max_length=100)


class StudentPasswordResetRequest(BaseModel):
    password: str = Field(..., min_length=6, max_length=100)


class StudentUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    password: Optional[str] = Field(default=None, min_length=6, max_length=100)
    status: Optional[str] = Field(default=None, pattern="^(active|inactive)$")


class StudentLoginRequest(BaseModel):
    # Either the roster id (preferred, stable) or the display name ??    # whichever the login form has in hand.
    studentId: Optional[str] = None
    name: Optional[str] = None
    password: str = Field(..., min_length=1, max_length=100)


class Student(BaseModel):
    id: str
    name: str
    createdAt: str


class TeacherCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=6, max_length=100)


class TeacherLoginRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=100)


class TeacherUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    password: Optional[str] = Field(default=None, min_length=6, max_length=100)
    status: Optional[str] = Field(default=None, pattern="^(active|inactive)$")


class RecordingQualityMetrics(BaseModel):
    duration_seconds: float = Field(default=0.0, ge=0.0)
    rms: float = Field(default=0.0, ge=0.0)
    peak: float = Field(default=0.0, ge=0.0)
    clipping_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    voiced_seconds: float = Field(default=0.0, ge=0.0)
    voiced_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    energy_variation: float = Field(default=0.0, ge=0.0)
    pitch_points: int = Field(default=0, ge=0)


class FeedbackQuality(BaseModel):
    """Evidence gate for student-facing automated feedback.

    ``status`` is one of reliable/review/retry.  A score is only suitable
    for mastery/progress decisions when its corresponding ``can_score_*``
    flag is true.  Reason codes are stable API values; ``student_message`` is
    presentation text and may evolve independently.
    """

    status: Literal["reliable", "review", "retry"] = "retry"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    can_score_pronunciation: bool = False
    can_score_content: bool = False
    reason_codes: List[str] = Field(default_factory=list)
    student_message: str = ""
    metrics: RecordingQualityMetrics = Field(default_factory=RecordingQualityMetrics)


class ProcessingTraceStage(BaseModel):
    stage: str
    status: str
    duration_ms: float = 0.0
    model: Optional[str] = None
    provider: Optional[str] = None
    detail: Optional[str] = None
    reason_codes: List[str] = Field(default_factory=list)
    # What this stage actually received/produced, for the teacher debugger's
    # per-step input/output cards. Deliberately compact (not the full
    # response) ??just this stage's own contract.
    input: Optional[Dict[str, Any]] = None
    output: Optional[Dict[str, Any]] = None


class ProcessingTrace(BaseModel):
    stages: List[ProcessingTraceStage] = Field(default_factory=list)
    total_duration_ms: float = 0.0


class ContentDiffSegment(BaseModel):
    type: Literal["match", "replace", "missing", "extra"]
    target: str = ""
    heard: str = ""


class AnalysisResponse(BaseModel):
    description: str = ""
    transcription: str = ""
    transcription_model: str = ""
    pitch_contour: List[Tuple[float, float]]
    word_prosody: List[dict]
    detected_tone: int
    tone_accuracy: float
    formants: dict
    vowel_quality: str = ""
    speech_rate: float
    fluency_score: float
    pitch_statistics: dict
    tone_direction: str = ""
    pause_analysis: dict = {}
    feedback: str
    ai_feedback: dict
    # Set only when the caller passed `verify_word` ??an independent real ASR
    # pass confirming whether the recording actually contains that word,
    # since `transcription` may have been supplied by the caller (not
    # detected) to score tone against a known target. None means no check
    # was requested (e.g. this wasn't a word-practice attempt).
    recognized_text: Optional[str] = None
    content_match: Optional[bool] = None
    content_diff: List[ContentDiffSegment] = Field(default_factory=list)
    feedback_quality: FeedbackQuality = Field(default_factory=FeedbackQuality)
    #: Sentence-level roll-up of the four-state tone diagnosis, plus the
    #: reason codes behind it. Diagnostic only: `controls_progression` is
    #: False and the lesson gate still runs on word_prosody[].passed.
    #: Per-syllable detail lives in word_prosody[].syllables[].
    tone_diagnostics: dict = Field(default_factory=dict)
    #: Backend-authoritative pronunciation gate used by the student UI. This
    #: is separate from the numeric tone score so a learner can see exactly
    #: whether every judged syllable cleared the current evidence threshold.
    pronunciation_mastery: dict = Field(default_factory=dict)
    #: Optional ACCEPT/UNCERTAIN/NEEDS_PRACTICE assistive layer (Candidate F1
    #: risk signal + Candidate E2 diagnostic, combined per the frozen
    #: `feedback_policy_protocol.json` rule). `None` unless
    #: `ENABLE_ASSISTIVE_FEEDBACK=1` is set AND the layer could compute a
    #: result for this utterance -- additive and diagnostic only, exactly
    #: like `tone_diagnostics`: does not touch `word_prosody[].passed` or
    #: any progression gate. The optional research integration is kept outside
    #: the production scoring modules.
    assistive_feedback: Optional[List[dict]] = None
    processing_trace: ProcessingTrace = Field(default_factory=ProcessingTrace)


class ReferenceToneResponse(BaseModel):
    tone: int
    name: str
    character: str
    pinyin: str
    description: str
    pitch_pattern: List[float]
    frequency_range: Tuple[int, int]
    expected_mean: int


