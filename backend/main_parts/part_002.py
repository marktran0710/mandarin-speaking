

class VocabDistractorResult(BaseModel):
    word: str
    distractors: List[str]


class VocabDistractorResponse(BaseModel):
    results: List[VocabDistractorResult]


class VocabClozeWord(BaseModel):
    word: str
    translation: str
    context: Optional[str] = None
    # Sentences already generated for this word (from a prior generation),
    # so a regeneration call tops up the pool with a genuinely new sentence
    # instead of the model repeating itself.
    avoid: List[str] = []


class VocabClozeRequest(BaseModel):
    words: List[VocabClozeWord]


class VocabClozeResult(BaseModel):
    word: str
    # A natural sentence containing `word` verbatim (the blank is cut client
    # side by replacing that occurrence — the model isn't asked to place a
    # blank marker itself, which it does unreliably).
    sentence: str
    # Wrong-but-plausible Chinese words that could grammatically fill the
    # same blank — the cloze question's multiple-choice options.
    distractors: List[str]


class VocabClozeResponse(BaseModel):
    results: List[VocabClozeResult]


class VocabSynonymWord(BaseModel):
    word: str
    translation: str
    context: Optional[str] = None
    # Synonyms already generated for this word (from a prior generation), so
    # a regeneration call tops up the pool with a genuinely new synonym
    # instead of the model repeating itself.
    avoid: List[str] = []


class VocabSynonymRequest(BaseModel):
    words: List[VocabSynonymWord]


class VocabSynonymResult(BaseModel):
    word: str
    # A real Chinese word/phrase with (nearly) the same meaning as `word`.
    synonym: str
    # Wrong-but-plausible Chinese words — NOT synonyms of `word` — for the
    # "which word means the same?" multiple-choice options.
    distractors: List[str]


class VocabSynonymResponse(BaseModel):
    results: List[VocabSynonymResult]


class AudioRecordRequest(BaseModel):
    id: str
    timestamp: str
    duration: int
    transcription: str = ""
    model: str
    topicId: Optional[str] = None
    studentId: Optional[str] = None
    imageUrl: Optional[str] = None
    imageIndex: Optional[int] = None
    audioUrl: Optional[str] = None
    audioName: Optional[str] = None
    praatMetrics: Optional[dict] = None
    analysisVersion: Optional[str] = None
    analysisSchemaVersion: Optional[str] = None
    modelVersion: Optional[str] = None
    comparisonGroupId: Optional[str] = None
    sessionId: Optional[str] = None
    attemptId: Optional[str] = None
    attemptNumber: Optional[int] = None
    attemptType: Optional[str] = None


class SpeakingProgressRequest(BaseModel):
    studentId: str
    topicId: str
    sceneIndex: int
    attempts: int = 0
    bestTone: float = 0
    bestFluency: float = 0
    masteryPassed: bool = False
    contentPassed: bool = False
    clearedWords: List[str] = []
    # The latest accepted per-scene submission snapshot. Kept nullable so
    # rows written before this field was introduced remain fully compatible.
    latestResult: Optional[Dict[str, Any]] = None
    # Additive story/prompt identity. The existing latest_result JSONB stores
    # these fields, so no speaking-progress table migration is required.
    baseStoryId: Optional[str] = Field(default=None, max_length=128)
    difficultyLevel: Optional[Literal["easy", "medium", "hard"]] = None
    promptId: Optional[str] = Field(default=None, max_length=200)


class CustomStoryFrameRequest(BaseModel):
    imageUrl: str
    imageUrlMedium: Optional[str] = None
    imageUrlHard: Optional[str] = None
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
    listenAudioSource: Optional[str] = None
    listenScript: Optional[str] = None
    vocabularyAudioUrls: Optional[str] = None
    vocabularyReferenceCurves: Optional[str] = None
    sentenceReferenceCurves: Optional[str] = None
    vocabularyDistractors: Optional[str] = None
    # JSON-encoded array of arrays (one entry per word, aligned with the
    # comma-split `vocabulary` above) — each word's entry is a list of
    # AI-generated {sentence, distractors} cloze candidates, grown over time
    # the same way vocabularyDistractors is (see vocab_quiz_cloze / the
    # vocabulary-cloze PATCH endpoint).
    vocabularyCloze: Optional[str] = None
    # JSON-encoded array of arrays (one entry per word) — each word's entry
    # is a list of AI-generated {synonym, distractors} candidates, grown the
    # same way vocabularyCloze is.
    vocabularySynonym: Optional[str] = None
    # Medium/Hard tiers of the same scene — same plot, just progressively
    # more complex text (and optionally its own image via imageUrlMedium/
    # imageUrlHard above). Absent/blank means that tier hasn't been authored
    # yet; the student-facing conversion falls back to the base (Easy) field
    # above rather than showing blank content.
    promptMedium: Optional[str] = None
    promptHard: Optional[str] = None
    vocabularyMedium: Optional[str] = None
    vocabularyHard: Optional[str] = None
    vocabularyPinyinMedium: Optional[str] = None
    vocabularyPinyinHard: Optional[str] = None
    vocabularyPosMedium: Optional[str] = None
    vocabularyPosHard: Optional[str] = None
    vocabularyTranslationMedium: Optional[str] = None
    vocabularyTranslationHard: Optional[str] = None
    phrasesMedium: Optional[str] = None
    phrasesHard: Optional[str] = None
    phrasesTranslationMedium: Optional[str] = None
    phrasesTranslationHard: Optional[str] = None
    suggestedAnswerMedium: Optional[str] = None
    suggestedAnswerHard: Optional[str] = None
    listenAudioUrlMedium: Optional[str] = None
    listenAudioUrlHard: Optional[str] = None
    listenAudioSourceMedium: Optional[str] = None
    listenAudioSourceHard: Optional[str] = None
    listenScriptMedium: Optional[str] = None
    listenScriptHard: Optional[str] = None
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
    # Canonical vocabulary and reusable phrases for the complete story,
    # keyed by difficulty tier (easy/medium/hard). These remain optional so
    # stories authored before story-level learning content was introduced
    # can still be read and re-saved unchanged.
    storyVocabulary: Optional[Dict[str, Dict[str, str]]] = None
    storyPhrases: Optional[Dict[str, Dict[str, str]]] = None
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
    difficultyLevel: Optional[Literal["easy", "medium", "hard"]] = None
    imageUrl: str = ""
    transcription: str = ""
    vocabUsed: List[str] = []
    vocabMissing: List[str] = []
    vocabScore: float = 0
    toneAccuracy: float = 0
    pronScore: float = 0
    fluencyScore: float = 0
    audioUrl: Optional[str] = None
    # Praat pause-analysis data for this scene's recording — see
    # ai_feedback.generate_story_feedback for why this now feeds story-level
    # feedback directly (delivery matters more once scenes can hand the
    # student a suggestedAnswer to read, since vocab/grammar aren't a choice).
    pauseCount: float = 0
    longestPause: float = 0
    utteranceCount: float = 0
    # Judged pause placement + articulation rate — see caf_metrics.classify_pauses
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
    level: Optional[Literal["easy", "medium", "hard"]] = None
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
    level: Optional[Literal["easy", "medium", "hard"]] = None
    completedAt: str
    totalQuestions: int = Field(..., ge=1)
    correctCount: int = Field(..., ge=0)
    totalTimeMs: int = Field(..., ge=0)
    questionResults: List[VocabQuizQuestionResult] = []


class StudentCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=6, max_length=100)


class StudentPasswordResetRequest(BaseModel):
    password: str = Field(..., min_length=6, max_length=100)


class StudentUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    password: Optional[str] = Field(default=None, min_length=6, max_length=100)
    status: Optional[str] = Field(default=None, pattern="^(active|inactive)$")


class QuizExclusion(BaseModel):
    """One piece of quiz material the teacher marked bad (see the teacher
    quiz-review page): a whole word ("word") or one candidate of a per-word
    AI pool ("cloze"/"synonym" with its pool index, or the whole
    "distractors" pool), or one deterministic question type ("pinyin" /
    "reverse")."""
    word: str = Field(..., min_length=1, max_length=50)
    kind: str = Field(..., pattern="^(word|cloze|synonym|distractors|pinyin|reverse)$")
    index: Optional[int] = Field(default=None, ge=0)


class QuizExclusionsUpdateRequest(BaseModel):
    exclusions: List[QuizExclusion]
    # The full per-word quiz material tree at save time, keyed by difficulty
    # tier (easy/medium/hard word text and pools can differ per tier), so
    # the Quiz Review page can diff live material against it next time
    # (new/changed/kept). Opaque here — the frontend owns the per-tier shape
    # and sends the whole map each time (merging in whichever tier changed),
    # so a save under one tier never clobbers another tier's baseline.
    materialSnapshot: Optional[Dict[str, List[dict]]] = None


class QuizClozeCandidateIn(BaseModel):
    sentence: str
    distractors: List[str] = []


class QuizSynonymCandidateIn(BaseModel):
    synonym: str
    distractors: List[str] = []


class QuizWordMaterialIn(BaseModel):
    """One word's current AI-generated quiz material, as the Quiz Review
    page already displays it (see storyToTopic/quizMaterialDiff) — the
    shape /quiz/validate and /quiz/approve both take, so the same JSON the
    frontend already builds for the diff snapshot can be sent as-is."""
    word: str
    translation: Optional[str] = None
    distractors: List[str] = []
    cloze: List[QuizClozeCandidateIn] = []
    synonym: List[QuizSynonymCandidateIn] = []


class QuizValidateRequest(BaseModel):
    words: List[QuizWordMaterialIn]
    exclusions: List[QuizExclusion] = []


class QuizValidateResultItem(BaseModel):
    word: str
    kind: str  # "translation" | "cloze" | "synonym" — matches the pools above
    poolIndex: Optional[int] = None
    status: str  # "clean" | "suspicious"
    reason: str = ""


class QuizValidateResponse(BaseModel):
    results: List[QuizValidateResultItem]


class QuizApproveRequest(BaseModel):
    level: str = Field(..., pattern="^(easy|medium|hard)$")
    # Selection-based, not exclusion-based: the caller builds this from only
    # the candidates a teacher explicitly checked in the opt-in review UI —
    # this becomes exactly what topicQuizEntries/storyToTopic serve students
    # for this tier once approved.
    material: List[QuizWordMaterialIn]


class QuizPendingApprovalsUpdateRequest(BaseModel):
    """The Quiz Review page's opt-in checkbox selections for one tier — not
    yet published (that's /quiz/approve), just surviving a page reload."""
    level: str = Field(..., pattern="^(easy|medium|hard)$")
    approvals: List[QuizExclusion]  # same {word, kind, index} shape, reused as-is


class QuizQuestionReplaceRequest(BaseModel):
    """Replaces one candidate's content in place — the existing vocabulary-*
    PATCH endpoints only merge new items into a pool, which can't fix an
    existing bad candidate's text. distractors has no poolIndex (editing it
    replaces the word's whole distractor list, matching how Quiz Review
    shows it as one row)."""
    frameIndex: int = Field(..., ge=0)
    wordIndex: int = Field(..., ge=0)
    kind: str = Field(..., pattern="^(translation|distractors|cloze|synonym|pinyin)$")
    poolIndex: Optional[int] = Field(default=None, ge=0)
    # Translation edits change the teacher-authored correct answer.  The
    # field is explicit because Medium/Hard can own a separate translation
    # list; omitting it keeps the existing Easy/base behaviour.
    translationField: Optional[str] = Field(
        default=None,
        pattern="^(vocabularyTranslation|vocabularyTranslationMedium|vocabularyTranslationHard)$",
    )
    # Pinyin edits follow the selected difficulty tier when that tier has
    # its own authored reading; otherwise the base vocabularyPinyin field is
    # used by the stories router.
    pinyinField: Optional[str] = Field(
        default=None,
        pattern="^(vocabularyPinyin|vocabularyPinyinMedium|vocabularyPinyinHard)$",
    )
    # distractors: List[str]; cloze: {sentence, distractors}; synonym: {synonym, distractors}
    # — a plain Any because the shape depends on `kind`; the handler validates it.
    value: Any


class StudentLoginRequest(BaseModel):
    # Either the roster id (preferred, stable) or the display name —
    # whichever the login form has in hand.
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


@app.get("/health")
def health_check():
    """Liveness endpoint with explicit database and upload-storage status.

    Keep this endpoint HTTP-200 so dashboards can inspect a degraded service;
    deployment platforms should use ``/health/ready`` when they need a strict
    readiness signal.
    """
    db_ok = False
    try:
        with connect_db() as db:
            db.execute("SELECT 1").fetchone()
        db_ok = True
    except Exception as exc:
        logger.error("Health check DB failure: %s", exc)
    storage_ok = False
    try:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        probe_path = os.path.join(UPLOAD_DIR, f".write-probe-{os.getpid()}")
        with open(probe_path, "wb") as probe:
            probe.write(b"ok")
        os.unlink(probe_path)
        storage_ok = True
    except OSError as exc:
        logger.error("Health check upload-storage failure: %s", exc)
    return {
        "status": "ok" if db_ok and storage_ok else "degraded",
        "service": "Speaking App Backend",
        "database": "ok" if db_ok else "error",
        "storage": "ok" if storage_ok else "error",
    }


@app.get("/health/ready")
async def readiness_check():
    """Strict readiness probe used by deployment platforms."""
    result = await health_check()
    if result["status"] != "ok":
        raise HTTPException(status_code=503, detail=result)
    return result
