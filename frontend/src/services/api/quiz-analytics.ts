import { BACKEND_URL, clientRoleHeader, fetchWithRetry } from "./client";

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
export interface VocabularyDistractorUpdate { frameIndex: number; wordIndex: number; distractors: string[]; }
export interface VocabularyClozeCandidate { sentence: string; distractors: string[]; }
export interface VocabularyClozeUpdate { frameIndex: number; wordIndex: number; candidates: VocabularyClozeCandidate[]; }
export interface VocabularySynonymCandidate { synonym: string; distractors: string[]; }
export interface VocabularySynonymUpdate { frameIndex: number; wordIndex: number; candidates: VocabularySynonymCandidate[]; }
export interface QuizValidateWord { word: string; translation?: string; distractors: string[]; cloze: Array<{ sentence: string; distractors: string[] }>; synonym: Array<{ synonym: string; distractors: string[] }>; }
export interface VocabQuizAttempt { id: string; storyId: string; studentName: string; studentId?: string; mode?: "tier1" | "tier2" | "tier3" | "speed" | "strikes" | "free" | "weak_words" | "maintenance_review" | "challenge"; baseStoryId?: string; level?: string; completedAt: string; totalQuestions: number; correctCount: number; totalTimeMs: number; questionResults: Array<{ word: string; correct: boolean; timeMs: number; itemId?: string; conceptId?: string; questionKind?: string; roundType?: "know_it" | "say_it" | "use_it"; knowledgeDimension?: "meaning" | "pinyin_production" | "contextual_recall"; activityType?: "diagnostic" | "personalized_practice" | "scheduled_maintenance" | "challenge" | "practice"; level?: string; baseStoryId?: string; itemVersion?: string; selectedAnswer?: string; correctAnswer?: string; presentedOptions?: string[]; questionPrompt?: string; answeredAt?: string; questionIndex?: number; lessonId?: string; quizId?: string; isBktEligible?: boolean; bktEligibilityErrors?: string[]; diagnosticExposureId?: string; assistedResponse?: boolean; bktValidationStatus?: "APPROVED" | "DRAFT" }>; }
async function patchPool(storyId: string, path: string, updates: unknown, message: string): Promise<void> {
  // Pool editing is teacher/admin work. Students can finish a quiz, but they
  // must not try to mutate published question material and receive a 403.
  if (clientRoleHeader() === "student") return;
  const response = await fetchWithRetry(`${BACKEND_URL}/api/custom-stories/${encodeURIComponent(storyId)}/${path}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ updates }) });
  if (!response.ok) throw new Error(message);
}
export function updateVocabularyDistractors(storyId: string, updates: VocabularyDistractorUpdate[]): Promise<void> { return patchPool(storyId, "vocabulary-distractors", updates, "Could not update vocabulary distractors for the story."); }
export function updateVocabularyCloze(storyId: string, updates: VocabularyClozeUpdate[]): Promise<void> { return patchPool(storyId, "vocabulary-cloze", updates, "Could not update vocabulary cloze questions for the story."); }
export function updateVocabularySynonym(storyId: string, updates: VocabularySynonymUpdate[]): Promise<void> { return patchPool(storyId, "vocabulary-synonym", updates, "Could not update vocabulary synonym questions for the story."); }
export async function updateQuizExclusions(storyId: string, exclusions: Array<{ word: string; kind: string; index?: number }>, materialSnapshot?: Record<string, unknown>): Promise<void> { const response = await fetchWithRetry(`${BACKEND_URL}/api/custom-stories/${encodeURIComponent(storyId)}/quiz-exclusions`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ exclusions, materialSnapshot }) }); if (!response.ok) throw new Error("Could not save the quiz exclusion list."); }
export async function approveQuizMaterial(storyId: string, level: string, material: QuizValidateWord[]): Promise<void> { const response = await fetchWithRetry(`${BACKEND_URL}/api/custom-stories/${encodeURIComponent(storyId)}/quiz/approve`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ level, material }) }); if (!response.ok) throw new Error("Could not publish the quiz."); }
export async function saveQuizPendingApprovals(storyId: string, level: string, approvals: Array<{ word: string; kind: string; index?: number }>): Promise<void> { const response = await fetchWithRetry(`${BACKEND_URL}/api/custom-stories/${encodeURIComponent(storyId)}/quiz-pending-approvals`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ level, approvals }) }); if (!response.ok) throw new Error("Could not save the quiz review selections."); }
export async function replaceQuizQuestion(storyId: string, frameIndex: number, wordIndex: number, kind: "translation" | "distractors" | "cloze" | "synonym" | "pinyin", poolIndex: number | undefined, value: string | string[] | { sentence: string; distractors: string[] } | { synonym: string; distractors: string[] }, translationField?: "vocabularyTranslation", pinyinField?: "vocabularyPinyin"): Promise<void> { const response = await fetchWithRetry(`${BACKEND_URL}/api/custom-stories/${encodeURIComponent(storyId)}/quiz-question`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ frameIndex, wordIndex, kind, poolIndex, value, translationField, pinyinField }) }); if (!response.ok) throw new Error("Could not save the edited question."); }
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
    // Round key stored in quiz_level — now tier1/tier2/tier3 (matches the mode).
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
// due maintenance reviews — a due word is never mislabelled "weak".
export interface ReviewQueueItem extends VocabPriorityReviewWord { reviewReason: "weak" | "due"; dueOn?: string | null; }
export interface VocabReviewQueueResponse extends VocabPriorityReviewResponse { queue: ReviewQueueItem[]; }
export async function getVocabQuizReviewQueue(storyId: string | undefined, studentId: string, options?: { includeAllWeak?: boolean }): Promise<VocabReviewQueueResponse> { const params = new URLSearchParams(); if (storyId) params.set("story_id", storyId); if (options?.includeAllWeak) params.set("include_all", "true"); const query = params.toString(); const response = await fetchWithRetry(withDevSrsToday(`${BACKEND_URL}/api/students/${encodeURIComponent(studentId)}/review-queue${query ? `?${query}` : ""}`)); if (!response.ok) throw new Error("Could not load the review queue."); return response.json() as Promise<VocabReviewQueueResponse>; }
/** Compatibility-shaped helper used by the existing per-story quiz picker.
 * The story picker asks for the complete cumulative weak-word set, while the
 * endpoint can still serve a smaller Bottom-K result to other callers. */
export type VocabWeakWordsResult = string[] & { diagnostic?: Pick<VocabPriorityReviewResponse, "unlocked" | "requiredDiagnosticQuizzes" | "completedDiagnosticQuizzes" | "diagnostic" | "diagnosticComplete" | "roundPresence">; priorityReview?: VocabPriorityReviewWord[]; mastery?: VocabPriorityReviewWord[] };
export async function getVocabQuizWeakWords(storyId: string, student: { studentId?: string; studentName?: string }): Promise<VocabWeakWordsResult> { if (!student.studentId) return []; const data = await getVocabQuizPriorityReview(storyId, student.studentId, { includeAllWeak: true }); const words = data.words.map((word) => word.word) as VocabWeakWordsResult; Object.defineProperty(words, "diagnostic", { value: { unlocked: data.unlocked, requiredDiagnosticQuizzes: data.requiredDiagnosticQuizzes, completedDiagnosticQuizzes: data.completedDiagnosticQuizzes, diagnostic: data.diagnostic, diagnosticComplete: data.diagnosticComplete, roundPresence: data.roundPresence }, enumerable: false }); Object.defineProperty(words, "priorityReview", { value: data.words, enumerable: false }); Object.defineProperty(words, "mastery", { value: data.mastery ?? [], enumerable: false }); return words; }
