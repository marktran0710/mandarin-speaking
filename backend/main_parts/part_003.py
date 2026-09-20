

MAX_VOCAB_DISTRACTORS_PER_WORD = 8


class VocabularyDistractorUpdate(BaseModel):
    frameIndex: int
    wordIndex: int
    distractors: List[str]


class VocabularyDistractorsUpdateRequest(BaseModel):
    updates: List[VocabularyDistractorUpdate]


# Lower than MAX_VOCAB_DISTRACTORS_PER_WORD: each cloze candidate bundles a
# whole sentence plus its own distractors, so a handful of varied sentences
# is plenty to avoid staleness without growing the pool unbounded.
MAX_VOCAB_CLOZE_PER_WORD = 4


class VocabularyClozeCandidate(BaseModel):
    sentence: str
    distractors: List[str]


class VocabularyClozeUpdate(BaseModel):
    frameIndex: int
    wordIndex: int
    candidates: List[VocabularyClozeCandidate]


class VocabularyClozeUpdateRequest(BaseModel):
    updates: List[VocabularyClozeUpdate]


MAX_VOCAB_SYNONYM_PER_WORD = 4


class VocabularySynonymCandidate(BaseModel):
    synonym: str
    distractors: List[str]


class VocabularySynonymUpdate(BaseModel):
    frameIndex: int
    wordIndex: int
    candidates: List[VocabularySynonymCandidate]


class VocabularySynonymUpdateRequest(BaseModel):
    updates: List[VocabularySynonymUpdate]


class GenerateModelVoiceRequest(BaseModel):
    frameIndex: int
    tier: str = "easy"


class GenerateModelVoiceBulkRequest(BaseModel):
    tiers: List[str] = ["easy"]


class TTSRequest(BaseModel):
    text: str
    voice: str = ""


ANALYZE_TIMEOUT_SECONDS = settings.analyze_timeout_seconds

# Caps how many /api/analyze requests run their CPU-bound stages (Praat,
# local ASR) at once. run_in_threadpool offloads this work off the event
# loop, but the threadpool itself has no size limit tied to actual CPU
# capacity - a classroom of ~50 students recording around the same moment
# would otherwise spin up dozens of CPU-heavy analyses simultaneously and
# thrash every core, making every single one slower rather than a few
# finishing quickly in sequence. Extra requests simply queue for a slot
# instead of being rejected; ANALYZE_TIMEOUT_SECONDS still bounds how long
# any one request (including its queue wait) can take.
ANALYZE_CONCURRENCY_LIMIT = settings.analyze_concurrency_limit
analyze_semaphore = asyncio.Semaphore(ANALYZE_CONCURRENCY_LIMIT)
ANALYZE_QUEUE_LIMIT = settings.analyze_queue_limit
