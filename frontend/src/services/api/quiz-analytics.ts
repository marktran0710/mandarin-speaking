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
export interface VocabQuizAttempt { id: string; storyId: string; studentName: string; studentId?: string; mode?: "tier1" | "tier2" | "tier3" | "speed" | "strikes" | "free" | "weak_words" | "maintenance_review" | "challenge"; baseStoryId?: string; level?: string; completedAt: string; totalQuestions: number; correctCount: number; totalTimeMs: number; questionResults: Array<{ word: string; correct: boolean; timeMs: number; itemId?: string; conceptId?: string; questionKind?: string; roundType?: "know_it" | "say_it" | "use_it"; knowledgeDimension?: "meaning" | "pinyin_production" | "contextual_recall"; activityType?: "diagnostic" | "personalized_practice" | "scheduled_maintenance" | "challenge" | "practice"; level?: string; baseStoryId?: string; itemVersion?: string; selectedAnswer?: string; correctAnswer?: string; presentedOptions?: string[]; questionPrompt?: string; answeredAt?: string; questionIndex?: number; lessonId?: string; quizId?: string; isBktEligible?: boolean; bktEligibilityErrors?: string[]; diagnosticExposureId?: string; assistedResponse?: boolean; bktValidationStatus?: "APPROVED" | "DRAFT" }>; }
export async function createVocabQuizAttempt(attempt: VocabQuizAttempt): Promise<VocabQuizAttempt> { const response = await fetchWithRetry(withDevSrsToday(`${BACKEND_URL}/api/vocab-quiz-attempts`), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(attempt) }); if (!response.ok) throw new Error("Could not save the vocabulary quiz attempt."); return response.json() as Promise<VocabQuizAttempt>; }
export async function recordVocabQuizResponse(attempt: VocabQuizAttempt): Promise<void> { const response = await fetchWithRetry(withDevSrsToday(`${BACKEND_URL}/api/vocab-quiz-responses`), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(attempt) }); if (!response.ok) throw new Error("Could not save the vocabulary quiz response."); }
export async function listVocabQuizAttempts(storyId?: string, student?: { studentId?: string; studentName?: string }, options?: { includeResults?: boolean }): Promise<VocabQuizAttempt[]> { const params = new URLSearchParams(); if (storyId) params.set("story_id", storyId); if (student?.studentId) params.set("student_id", student.studentId); else if (student?.studentName) params.set("student_name", student.studentName); if (options?.includeResults === false) params.set("include_results", "false"); const query = params.toString(); const response = await fetchWithRetry(query ? `${BACKEND_URL}/api/vocab-quiz-attempts?${query}` : `${BACKEND_URL}/api/vocab-quiz-attempts`); if (!response.ok) throw new Error("Could not load vocabulary quiz attempts."); const data = await response.json(); return Array.isArray(data) ? data : []; }
export type VocabularyReviewStatus = "NOT_ASSESSED" | "PROVISIONAL_REVIEW" | "NEEDS_PRACTICE" | "STRONG";
export type VocabularyDimension = "meaning" | "pinyin" | "context";
export interface VocabularyDimensionEvidence { total: number; correct: number; incorrect: number; lastResponseAt: string | null; }
export interface VocabularyState {
  evidence: { total: number; correct: number; incorrect: number; lastResponseAt: string | null; byDimension: Record<VocabularyDimension, VocabularyDimensionEvidence> };
  bkt: { pLearned: number; status: "UNASSESSED" | "DEVELOPING" | "STRONG"; modelVersion: string; parameterFingerprint: string };
  diagnostic: { status: "INCOMPLETE" | "COMPLETE"; completed: boolean };
  review: { status: VocabularyReviewStatus; candidate: boolean };
  practice: { status: "NOT_REQUIRED" | "PENDING" | "IN_PROGRESS" | "COMPLETE"; correctiveSuccesses: number; requiredSuccesses: number; failedDimensions: VocabularyDimension[]; successfulDimensions: VocabularyDimension[]; targetedSuccess: boolean };
  scheduling: { status: "NOT_SCHEDULED" | "SCHEDULED" | "DUE_FOR_REVIEW"; reps: number; ease: number | null; intervalDays: number; dueOn: string | null; lastReviewedOn: string | null };
}
/** Server vocabulary state. Legacy scalar fields remain optional only so old stored fixtures can render. */
export interface VocabPriorityReviewWord { wordId: string; word: string; meaning?: string | null; status: VocabularyReviewStatus; vocabularyState?: VocabularyState; pLearned?: number; observationCount?: number; correctCount?: number; incorrectCount?: number; reviewRank?: number | null; lastResponseAt?: string | null; lastItemId?: string | null; lessonId?: string | null; seenQuestionTypes?: string[]; failedQuestionTypes?: string[]; }
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
    roundType: "know_it" | "say_it" | "use_it";
    observedWords: number;
    observations: number;
    complete: boolean;
  }>;
}
export async function getVocabQuizPriorityReview(storyId: string | undefined, studentId: string, options?: { includeAllWeak?: boolean }): Promise<VocabPriorityReviewResponse> { const params = new URLSearchParams(); if (storyId) params.set("story_id", storyId); if (options?.includeAllWeak) params.set("include_all", "true"); const query = params.toString(); const response = await fetchWithRetry(`${BACKEND_URL}/api/students/${encodeURIComponent(studentId)}/weak-words${query ? `?${query}` : ""}`); if (!response.ok) throw new Error("Could not load personalized review."); return response.json() as Promise<VocabPriorityReviewResponse>; }
// One review-queue entry: a weak word (BKT low) or a due word (SM-2 schedule).
// `reviewReason` lets the UI show genuinely-weak words apart from mastered-but-
// due maintenance reviews ??a due word is never mislabelled "weak".
export interface ReviewQueueItem extends VocabPriorityReviewWord { reviewReason: "weak" | "due"; dueOn?: string | null; }
export interface VocabReviewQueueResponse extends VocabPriorityReviewResponse { queue: ReviewQueueItem[]; }
export async function getVocabQuizReviewQueue(storyId: string | undefined, studentId: string, options?: { includeAllWeak?: boolean }): Promise<VocabReviewQueueResponse> { const params = new URLSearchParams(); if (storyId) params.set("story_id", storyId); if (options?.includeAllWeak) params.set("include_all", "true"); const query = params.toString(); const response = await fetchWithRetry(withDevSrsToday(`${BACKEND_URL}/api/students/${encodeURIComponent(studentId)}/review-queue${query ? `?${query}` : ""}`)); if (!response.ok) throw new Error("Could not load the review queue."); return response.json() as Promise<VocabReviewQueueResponse>; }
/** Compatibility-shaped helper used by the existing per-story quiz picker.
 * The story picker asks for the complete cumulative weak-word set, while the
 * endpoint can still serve a smaller Bottom-K result to other callers. */
export type VocabWeakWordsResult = string[] & { diagnostic?: Pick<VocabPriorityReviewResponse, "unlocked" | "requiredDiagnosticQuizzes" | "completedDiagnosticQuizzes" | "diagnostic" | "diagnosticComplete" | "roundPresence">; priorityReview?: VocabPriorityReviewWord[]; mastery?: VocabPriorityReviewWord[] };
export async function getVocabQuizWeakWords(storyId: string, student: { studentId?: string; studentName?: string }): Promise<VocabWeakWordsResult> { if (!student.studentId) return []; const data = await getVocabQuizPriorityReview(storyId, student.studentId, { includeAllWeak: true }); const words = data.words.map((word) => word.word) as VocabWeakWordsResult; Object.defineProperty(words, "diagnostic", { value: { unlocked: data.unlocked, requiredDiagnosticQuizzes: data.requiredDiagnosticQuizzes, completedDiagnosticQuizzes: data.completedDiagnosticQuizzes, diagnostic: data.diagnostic, diagnosticComplete: data.diagnosticComplete, roundPresence: data.roundPresence }, enumerable: false }); Object.defineProperty(words, "priorityReview", { value: data.words, enumerable: false }); Object.defineProperty(words, "mastery", { value: data.mastery ?? [], enumerable: false }); return words; }

