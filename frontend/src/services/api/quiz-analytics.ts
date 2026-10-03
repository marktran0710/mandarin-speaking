import { BACKEND_URL, fetchWithRetry } from "@shared/api/client";

function devSrsToday(): string | undefined {
  if (!import.meta.env.DEV || typeof window === "undefined") return undefined;
  const value = new URLSearchParams(window.location.search).get("today");
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return undefined;
  const parsed = new Date(`${value}T00:00:00.000Z`);
  return Number.isNaN(parsed.valueOf()) || parsed.toISOString().slice(0, 10) !== value ? undefined : value;
}

function withDevSrsToday(path: string): string {
  const today = devSrsToday();
  if (!today) return path;
  return `${path}${path.includes("?") ? "&" : "?"}today=${encodeURIComponent(today)}`;
}
export interface VocabQuizAttempt { id: string; storyId: string; studentName: string; studentId?: string; vocabularyVersion?: number; mode?: "tier1" | "tier2" | "tier3" | "speed" | "strikes" | "free" | "weak_words" | "maintenance_review" | "challenge"; baseStoryId?: string; level?: string; completedAt: string; totalQuestions: number; correctCount: number; totalTimeMs: number; questionResults: Array<{ word: string; correct: boolean; timeMs: number; itemId?: string; conceptId?: string; questionKind?: string; round?: 1 | 2 | 3; tier?: "tier1" | "tier2" | "tier3"; knowledgeDimension?: "meaning" | "pinyin_production" | "contextual_recall"; activityType?: "diagnostic" | "personalized_practice" | "scheduled_maintenance" | "challenge" | "practice"; level?: string; baseStoryId?: string; itemVersion?: string; selectedAnswer?: string; correctAnswer?: string; presentedOptions?: string[]; questionPrompt?: string; answeredAt?: string; questionIndex?: number; lessonId?: string; quizId?: string; isBktEligible?: boolean; bktEligibilityErrors?: string[]; diagnosticExposureId?: string; assistedResponse?: boolean; bktValidationStatus?: "APPROVED" | "DRAFT" }>; }
export interface VocabularyProgressionTier { earned: boolean; correctCount: number; totalQuestions: number; /** 0–100, the latest finished attempt of this round. */ score: number; completedAt: string | null; }
export interface VocabularyProgression { storyId: string; quizStars: 0 | 1 | 2 | 3; requiredStars: number; tiers: Record<"tier1" | "tier2" | "tier3", VocabularyProgressionTier>; speakingUnlocked: boolean; conversationAvailable: boolean; conversationUnlocked: boolean; }
export class VocabularyChangedError extends Error {}

async function quizWriteError(response: Response): Promise<Error> {
  if (response.status === 409) {
    const data = await response.json().catch(() => ({})) as { detail?: string };
    if (typeof data.detail === "string" && data.detail.startsWith("Lesson vocabulary changed.")) {
      return new VocabularyChangedError(data.detail);
    }
  }
  return new Error("Could not save the vocabulary quiz.");
}
// The completed attempt is idempotent server-side (same id + same payload is
// accepted again), so it is safe to retry on a dropped connection or a
// gateway error — it is also the safety net for per-answer saves that failed.
export async function createVocabQuizAttempt(attempt: VocabQuizAttempt): Promise<VocabQuizAttempt> {
  const response = await fetchWithRetry(withDevSrsToday(`${BACKEND_URL}/api/vocab-quiz-attempts`), {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(attempt),
  }, 3, undefined, [502, 503, 504]);
  if (!response.ok) throw await quizWriteError(response);
  return response.json() as Promise<VocabQuizAttempt>;
}
export async function recordVocabQuizResponse(attempt: VocabQuizAttempt): Promise<void> {
  const response = await fetchWithRetry(withDevSrsToday(`${BACKEND_URL}/api/vocab-quiz-responses`), {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(attempt),
  });
  if (!response.ok) throw await quizWriteError(response);
}
export async function listVocabQuizAttempts(storyId?: string, student?: { studentId?: string; studentName?: string }, options?: { includeResults?: boolean; sinceDays?: number }): Promise<VocabQuizAttempt[]> { const params = new URLSearchParams(); if (storyId) params.set("story_id", storyId); if (student?.studentId) params.set("student_id", student.studentId); else if (student?.studentName) params.set("student_name", student.studentName); if (options?.includeResults === false) params.set("include_results", "false"); if (options?.sinceDays) params.set("since_days", String(options.sinceDays)); const query = params.toString(); const response = await fetchWithRetry(query ? `${BACKEND_URL}/api/vocab-quiz-attempts?${query}` : `${BACKEND_URL}/api/vocab-quiz-attempts`); if (!response.ok) throw new Error("Could not load vocabulary quiz attempts."); const data = await response.json(); return Array.isArray(data) ? data : []; }
export async function getVocabularyProgression(storyId: string, studentId: string): Promise<VocabularyProgression> { const response = await fetchWithRetry(`${BACKEND_URL}/api/students/${encodeURIComponent(studentId)}/vocabulary-progression?story_id=${encodeURIComponent(storyId)}`); if (!response.ok) throw new Error("Could not load vocabulary progression."); return response.json() as Promise<VocabularyProgression>; }
export type VocabularyReviewStatus = "NOT_ASSESSED" | "PROVISIONAL_REVIEW" | "NEEDS_PRACTICE" | "STRONG";
export type VocabularyDimension = "meaning" | "pinyin" | "context";
export interface VocabularyDimensionEvidence { total: number; correct: number; incorrect: number; lastResponseAt: string | null; }
export interface VocabularyState {
  evidence: { total: number; correct: number; incorrect: number; lastResponseAt: string | null; byDimension: Record<VocabularyDimension, VocabularyDimensionEvidence> };
  bkt: { pLearned: number; status: "UNASSESSED" | "DEVELOPING" | "STRONG"; modelVersion: string; parameterFingerprint: string };
  diagnostic: { status: "INCOMPLETE" | "COMPLETE"; completed: boolean; coveredDimensions: VocabularyDimension[]; coverageComplete: boolean };
  review: { status: VocabularyReviewStatus; candidate: boolean };
  /**
   * `unresolvedDimensions` is the single source of truth for what still needs
   * repair (a dimension is repaired by `requiredSuccesses` consecutive correct
   * corrective answers in that dimension). `nextDimension` is what the server
   * says to practice next; the client must not recompute it from history.
   */
  practice: {
    status: "NOT_REQUIRED" | "PENDING" | "IN_PROGRESS" | "COMPLETE";
    unresolvedDimensions: VocabularyDimension[];
    repairedDimensions: VocabularyDimension[];
    repairProgress: Partial<Record<VocabularyDimension, number>>;
    requiredSuccesses: number;
    nextDimension: VocabularyDimension | null;
    selectionReason: "repair_unresolved" | "complete_coverage" | "build_evidence" | null;
    policyVersion: string;
  };
  scheduling: { status: "NOT_SCHEDULED" | "SCHEDULED" | "DUE_FOR_REVIEW"; reps: number; ease: number | null; intervalDays: number; dueOn: string | null; lastReviewedOn: string | null };
}
/** Server vocabulary state. Legacy scalar fields remain optional only so old stored fixtures can render. */
export interface VocabPriorityReviewWord { wordId: string; word: string; meaning?: string | null; status: VocabularyReviewStatus; vocabularyState?: VocabularyState; pLearned?: number; observationCount?: number; correctCount?: number; incorrectCount?: number; reviewRank?: number | null; lastResponseAt?: string | null; lastItemId?: string | null; lessonId?: string | null; seenQuestionTypes?: string[]; }
export interface VocabPriorityReviewResponse {
  unlocked: boolean;
  requiredDiagnosticQuizzes: number;
  completedDiagnosticQuizzes: number;
  reviewCount: number;
  words: VocabPriorityReviewWord[];
  mastery?: VocabPriorityReviewWord[];
  diagnostic?: { status: "INCOMPLETE" | "COMPLETE"; unlocked?: boolean; requiredWords?: number; sufficientWords?: number; wordCoverage?: Record<string, number> };
  diagnosticComplete?: boolean;
  roundPresence?: Record<"tier1" | "tier2" | "tier3", {
    // Round key stored in quiz_level ??now tier1/tier2/tier3 (matches the mode).
    level: "tier1" | "tier2" | "tier3";
    round: 1 | 2 | 3;
    observedWords: number;
    observations: number;
    complete: boolean;
  }>;
}
export async function getVocabQuizPriorityReview(storyId: string | undefined, studentId: string, options?: { includeAllWeak?: boolean }): Promise<VocabPriorityReviewResponse> { const params = new URLSearchParams(); if (storyId) params.set("story_id", storyId); if (options?.includeAllWeak) params.set("include_all", "true"); const query = params.toString(); const response = await fetchWithRetry(`${BACKEND_URL}/api/students/${encodeURIComponent(studentId)}/weak-words${query ? `?${query}` : ""}`); if (!response.ok) throw new Error("Could not load personalized review."); return response.json() as Promise<VocabPriorityReviewResponse>; }
// One review-queue entry: a weak word (BKT low) or a due word (SM-2 schedule).
// `reviewReason` lets the UI show genuinely-weak words apart from mastered-but-
// due maintenance reviews ??a due word is never mislabelled "weak".
export interface ReviewQueueItem extends VocabPriorityReviewWord { reviewReason: "weak" | "due"; dueOn?: string | null; sourceStoryId?: string; sourceStoryIds?: string[]; vocabularyVersion?: number | null; }
export interface VocabReviewQueueResponse extends VocabPriorityReviewResponse { scope?: "lesson" | "all_learned"; queue: ReviewQueueItem[]; learnedStories?: Array<{ storyId: string; vocabularyVersion: number | null }>; learnedStoryCount?: number; }
export async function getVocabQuizReviewQueue(storyId: string | undefined, studentId: string, options?: { includeAllWeak?: boolean; scope?: "lesson" | "all_learned" }): Promise<VocabReviewQueueResponse> { const params = new URLSearchParams(); if (storyId) params.set("story_id", storyId); if (options?.includeAllWeak) params.set("include_all", "true"); if (options?.scope) params.set("scope", options.scope); const query = params.toString(); const response = await fetchWithRetry(withDevSrsToday(`${BACKEND_URL}/api/students/${encodeURIComponent(studentId)}/review-queue${query ? `?${query}` : ""}`)); if (!response.ok) throw new Error("Could not load the review queue."); return response.json() as Promise<VocabReviewQueueResponse>; }

export interface VocabReviewSessionQuestion {
  slotId: string;
  position: number;
  totalQuestions: number;
  word: string;
  sourceStoryId: string;
  questionType: string;
  dimension: "meaning" | "pinyin" | "context";
  reviewReason: "weak" | "due";
  answerFormat: "single_choice" | "free_text";
  prompt: string;
  options: string[];
}
export interface VocabReviewSession {
  sessionId: string;
  status: "active" | "completed" | "deferred" | "expired";
  questionCount: number;
  completedCount: number;
  currentQuestion: VocabReviewSessionQuestion | null;
}
export interface VocabReviewSessionStartResponse { session: VocabReviewSession | null; availableCount: number; }
export interface VocabReviewSessionAnswerResult {
  slotId: string;
  position: number;
  word: string;
  reviewReason: "weak" | "due";
  dimension: "meaning" | "pinyin" | "context";
  correct: boolean;
  correctAnswer: string;
  explanation: string;
  selectedAnswer: string;
  answeredAt: string;
}
export interface VocabReviewSessionAnswerResponse { result: VocabReviewSessionAnswerResult; session: VocabReviewSession; }
export class VocabReviewSessionError extends Error {
  constructor(message: string, readonly code?: string) { super(message); }
}
async function reviewSessionError(response: Response): Promise<VocabReviewSessionError> {
  const data = await response.json().catch(() => ({})) as { detail?: string | { code?: string; message?: string } };
  const detail = data.detail;
  if (typeof detail === "string") return new VocabReviewSessionError(detail);
  return new VocabReviewSessionError(
    detail?.message ?? "Could not save this review answer.",
    detail?.code,
  );
}
export async function startOrResumeVocabReviewSession(studentId: string): Promise<VocabReviewSessionStartResponse> {
  const response = await fetchWithRetry(withDevSrsToday(`${BACKEND_URL}/api/students/${encodeURIComponent(studentId)}/review-sessions`), {
    method: "POST",
  });
  if (!response.ok) throw await reviewSessionError(response);
  return response.json() as Promise<VocabReviewSessionStartResponse>;
}
export async function getVocabReviewSession(studentId: string, sessionId: string): Promise<VocabReviewSession> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/students/${encodeURIComponent(studentId)}/review-sessions/${encodeURIComponent(sessionId)}`);
  if (!response.ok) throw await reviewSessionError(response);
  return response.json() as Promise<VocabReviewSession>;
}
export async function answerVocabReviewSessionQuestion(
  studentId: string,
  sessionId: string,
  answer: { slotId: string; selectedAnswer: string; responseTimeMs: number },
): Promise<VocabReviewSessionAnswerResponse> {
  const response = await fetchWithRetry(withDevSrsToday(`${BACKEND_URL}/api/students/${encodeURIComponent(studentId)}/review-sessions/${encodeURIComponent(sessionId)}/answers`), {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(answer),
  });
  if (!response.ok) throw await reviewSessionError(response);
  return response.json() as Promise<VocabReviewSessionAnswerResponse>;
}
export async function deferVocabReviewSession(studentId: string, sessionId: string): Promise<VocabReviewSession> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/students/${encodeURIComponent(studentId)}/review-sessions/${encodeURIComponent(sessionId)}/defer`, {
    method: "POST",
  });
  if (!response.ok) throw await reviewSessionError(response);
  return response.json() as Promise<VocabReviewSession>;
}
/** Compatibility-shaped helper used by the existing per-story quiz picker.
 * The story picker asks for the complete cumulative weak-word set, while the
 * endpoint can still serve a smaller Bottom-K result to other callers. */
export type VocabWeakWordsResult = string[] & { diagnostic?: Pick<VocabPriorityReviewResponse, "unlocked" | "requiredDiagnosticQuizzes" | "completedDiagnosticQuizzes" | "diagnostic" | "diagnosticComplete" | "roundPresence">; priorityReview?: VocabPriorityReviewWord[]; mastery?: VocabPriorityReviewWord[] };
/** The review-queue payload is the weak-words payload plus `queue`, so one
 * response can feed both the weak-word card and the due-review list. */
export function weakWordsResultFromPriorityReview(data: VocabPriorityReviewResponse): VocabWeakWordsResult {
  const words = data.words.map((word) => word.word) as VocabWeakWordsResult;
  Object.defineProperty(words, "diagnostic", { value: { unlocked: data.unlocked, requiredDiagnosticQuizzes: data.requiredDiagnosticQuizzes, completedDiagnosticQuizzes: data.completedDiagnosticQuizzes, diagnostic: data.diagnostic, diagnosticComplete: data.diagnosticComplete, roundPresence: data.roundPresence }, enumerable: false });
  Object.defineProperty(words, "priorityReview", { value: data.words, enumerable: false });
  Object.defineProperty(words, "mastery", { value: data.mastery ?? [], enumerable: false });
  return words;
}
export async function getVocabQuizWeakWords(storyId: string, student: { studentId?: string; studentName?: string }): Promise<VocabWeakWordsResult> { if (!student.studentId) return []; const data = await getVocabQuizPriorityReview(storyId, student.studentId, { includeAllWeak: true }); return weakWordsResultFromPriorityReview(data); }

