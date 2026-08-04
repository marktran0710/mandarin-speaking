const BACKEND_URL =
  import.meta.env.VITE_BACKEND_URL ||
  (import.meta.env.DEV ? "http://127.0.0.1:8000" : "");

const REQUEST_TIMEOUT_MS = 15_000;
const VOCAB_GENERATION_RETRY_STATUSES = [429, 500, 502, 503, 504];

async function fetchWithRetry(
  input: RequestInfo | URL,
  init?: RequestInit,
  maxAttempts = 3,
  timeoutMs = REQUEST_TIMEOUT_MS,
  retryOnStatus: number[] = [],
): Promise<Response> {
  let lastError: unknown;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(input, { ...init, signal: controller.signal });
      clearTimeout(timer);
      if (retryOnStatus.includes(response.status) && attempt < maxAttempts) {
        await new Promise((r) => setTimeout(r, 300 * 2 ** (attempt - 1)));
        continue;
      }
      return response;
    } catch (err) {
      clearTimeout(timer);
      lastError = err;
      const isAbort = err instanceof DOMException && err.name === "AbortError";
      // Don't retry mutations to avoid double-writes unless callers explicitly opt in.
      const method = (init?.method ?? "GET").toUpperCase();
      if (
        isAbort ||
        (method !== "GET" && retryOnStatus.length === 0) ||
        attempt === maxAttempts
      ) {
        break;
      }
      await new Promise((r) => setTimeout(r, 300 * 2 ** (attempt - 1)));
    }
  }
  throw lastError;
}

export interface StoredAudioRecord {
  id: string;
  timestamp: string;
  duration: number;
  transcription: string;
  model: string;
  topicId?: string;
  studentId?: string | null;
  imageUrl?: string;
  imageIndex?: number;
  audioUrl?: string;
  praatMetrics?: any;
}

export interface StoredSpeakingProgress {
  studentId: string;
  topicId: string;
  sceneIndex: number;
  attempts: number;
  bestTone: number;
  bestFluency: number;
  masteryPassed: boolean;
  contentPassed: boolean;
  clearedWords: string[];
}

export interface CustomStoryFrame {
  imageUrl: string;
  prompt: string;
  vocabulary: string;
  vocabularyGroups?: Array<{ name: string; words: string[] }>;
  phrases?: string;
  phrasesTranslation?: string;
  vocabularyPinyin?: string;
  vocabularyPos?: string;
  vocabularyTranslation?: string;
  vocabularyDistractors?: string;
  // JSON-encoded array of arrays (one entry per word) — each word's entry
  // is a list of AI-generated {sentence, distractors} cloze candidates,
  // grown over time the same way vocabularyDistractors is.
  vocabularyCloze?: string;
  // JSON-encoded array of arrays (one entry per word) — each word's entry
  // is a list of AI-generated {synonym, distractors} candidates, grown the
  // same way vocabularyCloze is.
  vocabularySynonym?: string;
  suggestedAnswer?: string;
  listenAudioUrl?: string;
  listenScript?: string;
  // Medium/Hard tiers of the same scene — progressively more complex text,
  // and optionally their own image. Absent means that tier hasn't been
  // authored yet.
  imageUrlMedium?: string;
  imageUrlHard?: string;
  promptMedium?: string;
  promptHard?: string;
  vocabularyMedium?: string;
  vocabularyHard?: string;
  vocabularyPinyinMedium?: string;
  vocabularyPinyinHard?: string;
  vocabularyPosMedium?: string;
  vocabularyPosHard?: string;
  vocabularyTranslationMedium?: string;
  vocabularyTranslationHard?: string;
  phrasesMedium?: string;
  phrasesHard?: string;
  phrasesTranslationMedium?: string;
  phrasesTranslationHard?: string;
  suggestedAnswerMedium?: string;
  suggestedAnswerHard?: string;
  listenAudioUrlMedium?: string;
  listenAudioUrlHard?: string;
  listenScriptMedium?: string;
  listenScriptHard?: string;
}

export interface StoredCustomStory {
  id: string;
  title: string;
  learningGoal: string;
  frames: CustomStoryFrame[];
  published?: boolean;
  linear?: boolean;
  firstFrameIsExample?: boolean;
  lessonNumber?: number | null;
  lessonSubOrder?: number | null;
  narrativeMode?: NarrativeMode;
}

export type NarrativeMode = "story" | "describe" | "listen_retell";

export interface SceneSubmission {
  sceneIndex: number;
  imageUrl: string;
  transcription: string;
  vocabUsed: string[];
  vocabMissing: string[];
  vocabScore: number;
  toneAccuracy: number;
  pronScore: number;
  fluencyScore?: number;
  audioUrl?: string;
  // Delivery data from Praat's pause analysis on this scene's recording —
  // threaded through to story-level feedback so it can cite real pausing/
  // utterance behavior instead of just an opaque fluency percentage. Matters
  // more now that scenes can hand the student a suggestedAnswer to read
  // aloud, where vocabulary/grammar choice isn't really being tested but
  // delivery (pauses, utterance chunking) still is.
  pauseCount?: number;
  longestPause?: number;
  utteranceCount?: number;
  // Judged pause placement (mid-phrase vs. a natural clause/punctuation
  // boundary) and articulation rate — see backend caf_metrics.classify_pauses
  // and speech_rate_verdict for how these are derived.
  choppyPauseCount?: number;
  articulationRate?: number;
  // The student's own self-rating for this scene's accepted attempt, taken
  // right after they listened back to it and before they saw the system's
  // verdict — see SelfEvalStep. Absent when the student skipped the prompt.
  selfEvalContent?: "good" | "ok" | "bad";
  selfEvalPronunciation?: "good" | "ok" | "bad";
}

export interface StoryFeedbackDimension {
  score: number;
  feedback: string;
  judged?: boolean; // false = offline/local placeholder, not a real judgment
}

// Four pronunciation-focused dimensions, mirroring the same axes the radar
// chart already draws from Praat data (StoryFeedbackCard's
// computePronunciationProfile). Not IELTS-style vocabulary/grammar pillars —
// once a scene hands the student a script to read rather than compose
// freely, vocabulary/grammar choice isn't really being tested, only delivery
// is. See backend ai_feedback.fallback_story_feedback.
export interface StoryFeedback {
  provider: string;
  tone: StoryFeedbackDimension;
  word_stress: StoryFeedbackDimension;
  rhythm_pace: StoryFeedbackDimension;
  pausing: StoryFeedbackDimension;
}

export interface StorySubmission {
  id: string;
  storyId: string;
  storyTitle: string;
  studentName: string;
  studentId?: string;
  submittedAt: string;
  scenes: SceneSubmission[];
  concatenatedAudioUrl?: string | null;
  storyFeedback?: StoryFeedback | null;
  reviewStatus: "pending" | "reviewed";
  teacherNote?: string | null;
}

export interface HelpRequest {
  id: string;
  studentName: string;
  message: string;
  status: "open" | "resolved";
  createdAt: string;
  resolvedAt?: string | null;
}

export function canUseDatabase(): boolean {
  return Boolean(BACKEND_URL) && import.meta.env.MODE !== "test";
}

export async function listAudioRecords(params?: {
  limit?: number;
  skip?: number;
}): Promise<StoredAudioRecord[]> {
  const searchParams = new URLSearchParams();
  if (params?.limit !== undefined) searchParams.set("limit", String(params.limit));
  if (params?.skip !== undefined) searchParams.set("skip", String(params.skip));
  const query = searchParams.size > 0 ? `?${searchParams.toString()}` : "";
  const response = await fetchWithRetry(`${BACKEND_URL}/api/audio-records${query}`);
  if (!response.ok) {
    throw new Error("Could not load audio records from the database.");
  }

  const records = await response.json();
  return Array.isArray(records) ? records : [];
}

export async function getAudioRecordCount(): Promise<number> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/audio-records/count`);
  if (!response.ok) {
    throw new Error("Could not load audio record count from the database.");
  }

  const data = await response.json() as { total?: unknown };
  return typeof data.total === "number" ? data.total : 0;
}

export async function createAudioRecord(
  record: StoredAudioRecord,
  audioBlob?: Blob,
) {
  const response = audioBlob
    ? await uploadAudioRecord(record, audioBlob)
    : await fetchWithRetry(`${BACKEND_URL}/api/audio-records`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(record),
      });

  if (!response.ok) {
    throw new Error("Could not save audio record to the database.");
  }

  return response.json() as Promise<StoredAudioRecord>;
}

async function uploadAudioRecord(record: StoredAudioRecord, audioBlob: Blob) {
  const formData = new FormData();
  formData.append("record", JSON.stringify(record));
  formData.append("file", audioBlob, `${record.id}.wav`);

  return fetchWithRetry(`${BACKEND_URL}/api/audio-records/upload`, {
    method: "POST",
    body: formData,
  });
}

export async function listSpeakingProgress(
  studentId: string,
  topicId: string,
): Promise<StoredSpeakingProgress[]> {
  const response = await fetchWithRetry(
    `${BACKEND_URL}/api/speaking-progress?student_id=${encodeURIComponent(studentId)}&topic_id=${encodeURIComponent(topicId)}`,
  );
  if (!response.ok) {
    throw new Error("Could not load speaking progress from the database.");
  }
  const records = await response.json();
  return Array.isArray(records) ? records : [];
}

export async function saveSpeakingProgress(progress: StoredSpeakingProgress) {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/speaking-progress`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(progress),
  });
  if (!response.ok) {
    throw new Error("Could not save speaking progress to the database.");
  }
  return response.json() as Promise<StoredSpeakingProgress>;
}

export async function deleteAudioRecordFromDatabase(id: string) {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/audio-records/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    throw new Error("Could not delete audio record from the database.");
  }
}

export async function listCustomStories(): Promise<StoredCustomStory[]> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/custom-stories`);
  if (!response.ok) {
    throw new Error("Could not load custom stories from the database.");
  }

  const stories = await response.json();
  return Array.isArray(stories) ? stories : [];
}

export async function createCustomStory(
  story: StoredCustomStory,
): Promise<StoredCustomStory> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/custom-stories`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(story),
  });

  if (!response.ok) {
    throw new Error("Could not save custom story to the database.");
  }

  // The backend writes any uploaded data-URL images to disk and returns the
  // frames with lightweight /uploads/images/... URLs in their place.
  return response.json() as Promise<StoredCustomStory>;
}

export async function deleteCustomStoryFromDatabase(id: string) {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/custom-stories/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    throw new Error("Could not delete custom story from the database.");
  }
}

export interface VocabGrowthWord {
  word: string;
  translation: string;
  context?: string;
  avoid: string[];
}

/** The four raw AI-generation endpoints StoryRecorder's background pool
 * growth already calls inline — exposed as reusable service functions so
 * TeacherQuizReviewPage's "Generate/Update Questions" can call the exact
 * same generation the app already relies on, just staged for teacher
 * accept/reject instead of merged in immediately. */
export async function generateVocabDistractors(
  words: VocabGrowthWord[],
): Promise<Array<{ word: string; distractors: string[] }>> {
  const response = await fetchWithRetry(
    `${BACKEND_URL}/api/vocab-quiz-distractors`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ words }),
    },
    3,
    REQUEST_TIMEOUT_MS,
    VOCAB_GENERATION_RETRY_STATUSES,
  );
  if (!response.ok) throw new Error("Could not generate new quiz distractors.");
  const { results } = (await response.json()) as { results: Array<{ word: string; distractors: string[] }> };
  return results;
}

export async function generateVocabCloze(
  words: VocabGrowthWord[],
): Promise<Array<{ word: string; sentence: string; distractors: string[] }>> {
  const response = await fetchWithRetry(
    `${BACKEND_URL}/api/vocab-quiz-cloze`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ words }),
    },
    3,
    REQUEST_TIMEOUT_MS,
    VOCAB_GENERATION_RETRY_STATUSES,
  );
  if (!response.ok) throw new Error("Could not generate new quiz cloze questions.");
  const { results } = (await response.json()) as {
    results: Array<{ word: string; sentence: string; distractors: string[] }>;
  };
  return results;
}

export async function generateVocabSynonym(
  words: VocabGrowthWord[],
): Promise<Array<{ word: string; synonym: string; distractors: string[] }>> {
  const response = await fetchWithRetry(
    `${BACKEND_URL}/api/vocab-quiz-synonym`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ words }),
    },
    3,
    REQUEST_TIMEOUT_MS,
    VOCAB_GENERATION_RETRY_STATUSES,
  );
  if (!response.ok) throw new Error("Could not generate new quiz synonym questions.");
  const { results } = (await response.json()) as {
    results: Array<{ word: string; synonym: string; distractors: string[] }>;
  };
  return results;
}

export async function generateVocabLookalike(
  words: VocabGrowthWord[],
): Promise<Array<{ word: string; lookalikes: string[] }>> {
  const response = await fetchWithRetry(
    `${BACKEND_URL}/api/vocab-quiz-lookalike`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ words }),
    },
    3,
    REQUEST_TIMEOUT_MS,
    VOCAB_GENERATION_RETRY_STATUSES,
  );
  if (!response.ok) throw new Error("Could not generate new look-alike traps.");
  const { results } = (await response.json()) as { results: Array<{ word: string; lookalikes: string[] }> };
  return results;
}

export interface VocabularyDistractorUpdate {
  frameIndex: number;
  wordIndex: number;
  distractors: string[];
}

// Tops up a story's persisted per-word distractor pool (merged/deduped/capped
// server-side) rather than replacing it — called after a student finishes a
// vocab quiz round so the pool grows over time instead of staying fixed at
// whatever the teacher generated once at authoring time.
export async function updateVocabularyDistractors(
  storyId: string,
  updates: VocabularyDistractorUpdate[],
): Promise<void> {
  const response = await fetchWithRetry(
    `${BACKEND_URL}/api/custom-stories/${encodeURIComponent(storyId)}/vocabulary-distractors`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ updates }),
    },
  );

  if (!response.ok) {
    throw new Error("Could not update vocabulary distractors for the story.");
  }
}

export interface VocabularyLookalikeUpdate {
  frameIndex: number;
  wordIndex: number;
  lookalikes: string[];
}

// Tops up a story's persisted per-word look-alike pool (the tier-3 quiz's
// face-confusion traps), mirroring updateVocabularyDistractors above.
export async function updateVocabularyLookalike(
  storyId: string,
  updates: VocabularyLookalikeUpdate[],
): Promise<void> {
  const response = await fetchWithRetry(
    `${BACKEND_URL}/api/custom-stories/${encodeURIComponent(storyId)}/vocabulary-lookalike`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ updates }),
    },
  );

  if (!response.ok) {
    throw new Error("Could not update vocabulary look-alikes for the story.");
  }
}

export interface VocabularyClozeCandidate {
  sentence: string;
  distractors: string[];
}

export interface VocabularyClozeUpdate {
  frameIndex: number;
  wordIndex: number;
  candidates: VocabularyClozeCandidate[];
}

// Tops up a story's persisted per-word cloze-question pool (merged/deduped/
// capped server-side) rather than replacing it — mirrors
// updateVocabularyDistractors above, called after a student finishes a vocab
// quiz round so cloze sentences keep varying over time.
/** Replaces a story's teacher-marked bad-quiz-material list (see
 * TeacherQuizReviewPage) — PUT semantics, the full current set each time.
 * `materialSnapshot`, when passed, is stamped in the same request as the
 * new diff baseline (custom_stories.quiz_material_snapshot) — the whole
 * per-tier map, per withUpdatedSnapshot; omitting it leaves the stored
 * snapshot untouched. */
export async function updateQuizExclusions(
  storyId: string,
  exclusions: Array<{ word: string; kind: string; index?: number }>,
  materialSnapshot?: Record<string, unknown>,
): Promise<void> {
  const response = await fetchWithRetry(
    `${BACKEND_URL}/api/custom-stories/${encodeURIComponent(storyId)}/quiz-exclusions`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ exclusions, materialSnapshot }),
    },
  );
  if (!response.ok) {
    throw new Error("Could not save the quiz exclusion list.");
  }
}

export interface QuizValidateWord {
  word: string;
  translation?: string;
  distractors: string[];
  cloze: Array<{ sentence: string; distractors: string[] }>;
  synonym: Array<{ synonym: string; distractors: string[] }>;
  lookalike: string[];
}

export interface QuizValidateResultItem {
  word: string;
  kind: "translation" | "distractors" | "cloze" | "synonym";
  poolIndex?: number;
  status: "clean" | "suspicious";
  reason: string;
}

/** Runs the adversarial validation pipeline (blind solver + judge, no
 * auto-repair) against a story's *current* live quiz material — read-only,
 * nothing is written. A 60s timeout: a full lesson's worth of words is
 * several sequential LLM batches, not a quick fetch. */
export async function validateQuizMaterial(
  storyId: string,
  words: QuizValidateWord[],
  exclusions: Array<{ word: string; kind: string; index?: number }>,
): Promise<QuizValidateResultItem[]> {
  const response = await fetchWithRetry(
    `${BACKEND_URL}/api/custom-stories/${encodeURIComponent(storyId)}/quiz/validate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ words, exclusions }),
    },
    3,
    60_000,
  );
  if (!response.ok) {
    throw new Error("Could not validate the quiz questions.");
  }
  const { results } = (await response.json()) as { results: QuizValidateResultItem[] };
  return results;
}

/** The only call that changes what students are served: writes
 * custom_stories.quiz_approved_snapshot for one tier. `material` is built
 * by the caller from only the candidates a teacher explicitly checked in
 * the opt-in review UI (see utils/quizApprovedMaterial.ts's
 * buildApprovedMaterial). */
export async function approveQuizMaterial(
  storyId: string,
  level: string,
  material: QuizValidateWord[],
): Promise<void> {
  const response = await fetchWithRetry(
    `${BACKEND_URL}/api/custom-stories/${encodeURIComponent(storyId)}/quiz/approve`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ level, material }),
    },
  );
  if (!response.ok) {
    throw new Error("Could not publish the quiz.");
  }
}

/** Saves the Quiz Review page's opt-in checkbox selections for one tier —
 * not a publish action (see approveQuizMaterial), just persistence so a
 * teacher's in-progress review survives a reload. PUT semantics: the full
 * current set each time, mirroring updateQuizExclusions. */
export async function saveQuizPendingApprovals(
  storyId: string,
  level: string,
  approvals: Array<{ word: string; kind: string; index?: number }>,
): Promise<void> {
  const response = await fetchWithRetry(
    `${BACKEND_URL}/api/custom-stories/${encodeURIComponent(storyId)}/quiz-pending-approvals`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ level, approvals }),
    },
  );
  if (!response.ok) {
    throw new Error("Could not save the quiz review selections.");
  }
}

/** Replaces one candidate's content in place (Quiz Review's inline Edit) —
 * unlike updateVocabularyDistractors/-Cloze/-Synonym, which only merge new
 * items into a pool and can't fix an existing bad candidate's text.
 * `value` is a string for "translation", a string[] for "distractors" (the word's whole list, no
 * poolIndex — Quiz Review shows it as one row) or {sentence,distractors} /
 * {synonym,distractors} for "cloze" / "synonym" at `poolIndex`. */
export async function replaceQuizQuestion(
  storyId: string,
  frameIndex: number,
  wordIndex: number,
  kind: "translation" | "distractors" | "cloze" | "synonym",
  poolIndex: number | undefined,
  value: string | string[] | { sentence: string; distractors: string[] } | { synonym: string; distractors: string[] },
  translationField?: "vocabularyTranslation" | "vocabularyTranslationMedium" | "vocabularyTranslationHard",
): Promise<void> {
  const response = await fetchWithRetry(
    `${BACKEND_URL}/api/custom-stories/${encodeURIComponent(storyId)}/quiz-question`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ frameIndex, wordIndex, kind, poolIndex, value, translationField }),
    },
  );
  if (!response.ok) {
    throw new Error("Could not save the edited question.");
  }
}

export async function updateVocabularyCloze(
  storyId: string,
  updates: VocabularyClozeUpdate[],
): Promise<void> {
  const response = await fetchWithRetry(
    `${BACKEND_URL}/api/custom-stories/${encodeURIComponent(storyId)}/vocabulary-cloze`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ updates }),
    },
  );

  if (!response.ok) {
    throw new Error("Could not update vocabulary cloze questions for the story.");
  }
}

export interface VocabularySynonymCandidate {
  synonym: string;
  distractors: string[];
}

export interface VocabularySynonymUpdate {
  frameIndex: number;
  wordIndex: number;
  candidates: VocabularySynonymCandidate[];
}

// Tops up a story's persisted per-word synonym-question pool, mirroring
// updateVocabularyCloze above.
export async function updateVocabularySynonym(
  storyId: string,
  updates: VocabularySynonymUpdate[],
): Promise<void> {
  const response = await fetchWithRetry(
    `${BACKEND_URL}/api/custom-stories/${encodeURIComponent(storyId)}/vocabulary-synonym`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ updates }),
    },
  );

  if (!response.ok) {
    throw new Error("Could not update vocabulary synonym questions for the story.");
  }
}

export async function listHelpRequests(): Promise<HelpRequest[]> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/help-requests`);
  if (!response.ok) {
    throw new Error("Could not load help requests from the database.");
  }

  const requests = await response.json();
  return Array.isArray(requests) ? requests : [];
}

export async function createHelpRequest(request: HelpRequest) {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/help-requests`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error("Could not send the help request.");
  }

  return response.json() as Promise<HelpRequest>;
}

export async function listStorySubmissions(storyId?: string): Promise<StorySubmission[]> {
  const url = storyId
    ? `${BACKEND_URL}/api/story-submissions?story_id=${encodeURIComponent(storyId)}`
    : `${BACKEND_URL}/api/story-submissions`;
  const response = await fetchWithRetry(url);
  if (!response.ok) throw new Error("Could not load story submissions.");
  const data = await response.json();
  return Array.isArray(data) ? data : [];
}

export async function createStorySubmission(
  submission: Omit<StorySubmission, "reviewStatus" | "teacherNote">,
): Promise<StorySubmission> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/story-submissions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(submission),
  });
  if (!response.ok) throw new Error("Could not submit story.");
  return response.json() as Promise<StorySubmission>;
}

export async function updateSubmissionReview(
  id: string,
  status: "pending" | "reviewed",
  note?: string | null,
): Promise<StorySubmission> {
  const response = await fetchWithRetry(
    `${BACKEND_URL}/api/story-submissions/${encodeURIComponent(id)}/review`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status, note }),
    },
  );
  if (!response.ok) {
    throw new Error("Could not update story submission review.");
  }
  return response.json() as Promise<StorySubmission>;
}

export interface VocabQuizAttempt {
  id: string;
  storyId: string;
  studentName: string;
  // Optional: attempts saved before the student roster existed have none —
  // student_name (free-typed, collision-prone) is the only join key for
  // those legacy rows.
  studentId?: string;
  // Optional: attempts saved before quiz mode was tracked have none.
  // tier1/2/3 are the star-tier runs (see quizTiers.ts); speed/strikes are
  // legacy modes kept for old rows.
  mode?: "tier1" | "tier2" | "tier3" | "speed" | "strikes" | "free" | "weak_words";
  completedAt: string;
  totalQuestions: number;
  correctCount: number;
  totalTimeMs: number;
  questionResults: Array<{ word: string; correct: boolean; timeMs: number }>;
}

export async function createVocabQuizAttempt(
  attempt: VocabQuizAttempt,
): Promise<VocabQuizAttempt> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/vocab-quiz-attempts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(attempt),
  });
  if (!response.ok) throw new Error("Could not save the vocabulary quiz attempt.");
  return response.json() as Promise<VocabQuizAttempt>;
}

export async function listVocabQuizAttempts(
  storyId?: string,
  student?: { studentId?: string; studentName?: string },
): Promise<VocabQuizAttempt[]> {
  const params = new URLSearchParams();
  if (storyId) params.set("story_id", storyId);
  if (student?.studentId) params.set("student_id", student.studentId);
  else if (student?.studentName) params.set("student_name", student.studentName);
  const query = params.toString();
  const url = query
    ? `${BACKEND_URL}/api/vocab-quiz-attempts?${query}`
    : `${BACKEND_URL}/api/vocab-quiz-attempts`;
  const response = await fetchWithRetry(url);
  if (!response.ok) throw new Error("Could not load vocabulary quiz attempts.");
  const data = await response.json();
  return Array.isArray(data) ? data : [];
}

// Words in a story whose most recent quiz answer (any past attempt, any
// mode) was wrong — powers the persistent "weak words" quiz mode, distinct
// from the same-session-only missed-words retry inside StoryVocabQuiz.
export async function getVocabQuizWeakWords(
  storyId: string,
  student: { studentId?: string; studentName?: string },
): Promise<string[]> {
  const params = new URLSearchParams({ story_id: storyId });
  if (student.studentId) params.set("student_id", student.studentId);
  else if (student.studentName) params.set("student_name", student.studentName);
  else return [];
  const response = await fetchWithRetry(
    `${BACKEND_URL}/api/vocab-quiz-attempts/weak-words?${params.toString()}`,
  );
  if (!response.ok) throw new Error("Could not load weak words.");
  const data = await response.json();
  return Array.isArray(data?.words) ? data.words : [];
}

export async function resolveHelpRequest(id: string) {
  const response = await fetchWithRetry(
    `${BACKEND_URL}/api/help-requests/${encodeURIComponent(id)}/resolve`,
    { method: "POST" },
  );

  if (!response.ok) {
    throw new Error("Could not resolve the help request.");
  }

  return response.json() as Promise<HelpRequest>;
}

// ── Student roster ─────────────────────────────────────────────────────
// A stable id per student, curated by a teacher, instead of the free-typed
// name string every attempt used to carry (collision- and typo-prone, and
// no real join key for per-student analysis).
export interface Student {
  id: string;
  name: string;
  createdAt: string;
}

export async function listStudents(): Promise<Student[]> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/students`);
  if (!response.ok) throw new Error("Could not load the student roster.");
  const data = await response.json();
  return Array.isArray(data) ? data : [];
}

/** Password check for the student login page (default 123456). Throws with
 * `notFound` (no student with that name — may just be new) kept distinct
 * from `wrongCredentials` (that name exists, password didn't match), so a
 * caller can let a brand-new name join on the default password without
 * also letting a wrong guess at an *existing* name slip through as a
 * "new" signup. */
export async function loginStudent(params: {
  studentId?: string;
  name?: string;
  password: string;
}): Promise<Student> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/students/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (response.status === 401 || response.status === 404) {
    const error = new Error("Wrong name or password.");
    (error as Error & { wrongCredentials?: boolean; notFound?: boolean }).wrongCredentials = true;
    (error as Error & { wrongCredentials?: boolean; notFound?: boolean }).notFound = response.status === 404;
    throw error;
  }
  if (!response.ok) throw new Error("Could not sign in.");
  return response.json() as Promise<Student>;
}

export async function createStudent(name: string): Promise<Student> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/students`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!response.ok) throw new Error("Could not add the student to the roster.");
  return response.json() as Promise<Student>;
}

export async function deleteStudent(id: string): Promise<void> {
  const response = await fetchWithRetry(
    `${BACKEND_URL}/api/students/${encodeURIComponent(id)}`,
    { method: "DELETE" },
  );
  if (!response.ok) throw new Error("Could not remove the student from the roster.");
}
