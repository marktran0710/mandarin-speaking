import type { VocabPriorityReviewWord, VocabQuizAttempt } from "../../services/api/quiz-analytics";
import type { VocabQuizEntry, VocabQuizSummary } from "./model";

export type LearnerVocabularyStatus = "strong" | "developing" | "needs_practice";

export interface VocabularyImprovement {
  wordId: string;
  targetWord: string;
  initialStatus: LearnerVocabularyStatus;
  finalStatus: LearnerVocabularyStatus;
  strengthenedThroughPractice: boolean;
}

export interface LessonRoundProgress {
  completed: boolean;
  answered: number;
  total: number;
  correct: number;
  accuracy: number;
}

export interface LessonVocabularyProgress {
  lessonId: string;
  totalWords: number;
  strongWords: number;
  remainingWords: number;
  vocabularyReviewCompleted: boolean;
  knowIt: LessonRoundProgress;
  sayIt: LessonRoundProgress;
  useIt: LessonRoundProgress;
  strengthen: {
    required: number;
    strengthened: number;
    remaining: number;
    completed: boolean;
  };
  lessonCompleted: boolean;
  challenge: {
    available: boolean;
    attempts: number;
    lastScore?: number;
    bestScore?: number;
  };
  initialStrongCount: number;
  strengthenedCount: number;
  improvements: VocabularyImprovement[];
  focusWords: VocabPriorityReviewWord[];
}

export interface LessonProgressSnapshot {
  initialStatuses: Record<string, LearnerVocabularyStatus>;
  initialStrongCount?: number;
  challengeBestScore?: number;
  attempts?: VocabQuizAttempt[];
}

const STATUS_ORDER: LearnerVocabularyStatus[] = ["needs_practice", "developing", "strong"];
const SNAPSHOT_KEY = "mandarin-speaking.lesson-vocabulary-progress.v1";

function entryId(entry: Pick<VocabQuizEntry, "wordId" | "word">): string {
  return (entry.wordId || entry.word).normalize("NFKC").trim().replace(/\s+/g, " ");
}

export function learnerStatus(status: VocabPriorityReviewWord["status"] | undefined): LearnerVocabularyStatus {
  if (status === "MASTERED") return "strong";
  if (status === "DEVELOPING") return "developing";
  return "needs_practice";
}

function emptyRound(): LessonRoundProgress {
  return { completed: false, answered: 0, total: 0, correct: 0, accuracy: 0 };
}

function roundFromAttempt(attempt: VocabQuizAttempt | undefined): LessonRoundProgress {
  if (!attempt) return emptyRound();
  const results = attempt.questionResults || [];
  const answered = results.length || attempt.totalQuestions || 0;
  const total = Math.max(answered, attempt.totalQuestions || 0);
  const correct = results.length ? results.filter((result) => result.correct).length : attempt.correctCount || 0;
  return {
    completed: true,
    answered,
    total,
    correct,
    accuracy: total > 0 ? Math.round((correct / total) * 100) : 0,
  };
}

function latestAttempt(attempts: VocabQuizAttempt[], mode: VocabQuizAttempt["mode"]): VocabQuizAttempt | undefined {
  return attempts
    .filter((attempt) => attempt.mode === mode)
    .sort((a, b) => new Date(b.completedAt).getTime() - new Date(a.completedAt).getTime())[0];
}

function mergeCurrentAttempt(attempts: VocabQuizAttempt[], current?: VocabQuizSummary): VocabQuizAttempt[] {
  if (!current) return attempts;
  return [...attempts, {
    id: "current-session",
    storyId: "current-session",
    studentName: "Student",
    mode: current.mode,
    completedAt: new Date().toISOString(),
    totalQuestions: current.totalQuestions,
    correctCount: current.correctCount,
    totalTimeMs: current.totalTimeMs,
    questionResults: current.questionResults,
  }];
}

function snapshotStorageKey(studentScope: string | undefined, lessonId: string): string {
  return `${SNAPSHOT_KEY}:${studentScope || "anonymous"}:${lessonId}`;
}

export function loadLessonProgressSnapshot(studentScope: string | undefined, lessonId: string): LessonProgressSnapshot {
  if (typeof window === "undefined") return { initialStatuses: {} };
  try {
    const raw = window.localStorage.getItem(snapshotStorageKey(studentScope, lessonId));
    const value = raw ? JSON.parse(raw) as Partial<LessonProgressSnapshot> : {};
    return {
      initialStatuses: value.initialStatuses && typeof value.initialStatuses === "object" ? value.initialStatuses : {},
      initialStrongCount: typeof value.initialStrongCount === "number" ? value.initialStrongCount : undefined,
      challengeBestScore: typeof value.challengeBestScore === "number" ? value.challengeBestScore : undefined,
      attempts: Array.isArray(value.attempts) ? value.attempts : [],
    };
  } catch {
    return { initialStatuses: {} };
  }
}

export function saveLessonAttempt(
  studentScope: string | undefined,
  lessonId: string,
  attempt: VocabQuizAttempt,
): LessonProgressSnapshot {
  const snapshot = loadLessonProgressSnapshot(studentScope, lessonId);
  const attempts = [...(snapshot.attempts || []).filter((item) => item.id !== attempt.id), attempt].slice(-40);
  const challengeAttempts = attempts.filter((item) => item.mode === "challenge");
  const challengeBestScore = challengeAttempts.length
    ? Math.max(...challengeAttempts.map((item) => item.correctCount))
    : snapshot.challengeBestScore;
  const next = { ...snapshot, attempts, challengeBestScore };
  saveLessonProgressSnapshot(studentScope, lessonId, next);
  return next;
}

export function saveLessonProgressSnapshot(
  studentScope: string | undefined,
  lessonId: string,
  snapshot: LessonProgressSnapshot,
): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(snapshotStorageKey(studentScope, lessonId), JSON.stringify(snapshot));
  } catch {
    /* Progress remains available from the server when browser storage is unavailable. */
  }
}

function currentStatuses(
  entries: VocabQuizEntry[],
  mastery: VocabPriorityReviewWord[],
): Map<string, LearnerVocabularyStatus> {
  const byId = new Map(mastery.map((word) => [word.wordId, learnerStatus(word.status)]));
  const byWord = new Map(mastery.map((word) => [word.word, learnerStatus(word.status)]));
  return new Map(entries.map((entry) => [
    entryId(entry),
    byId.get(entry.wordId || "") ?? byWord.get(entry.word) ?? "needs_practice",
  ]));
}

function recordInitialStatuses(
  snapshot: LessonProgressSnapshot,
  statuses: Map<string, LearnerVocabularyStatus>,
  diagnosticComplete: boolean,
  totalWords: number,
  studentScope: string | undefined,
  lessonId: string,
): LessonProgressSnapshot {
  if (!diagnosticComplete || statuses.size === 0) return snapshot;
  const initialStatuses = { ...snapshot.initialStatuses };
  statuses.forEach((status, id) => { if (!initialStatuses[id]) initialStatuses[id] = status; });
  const initialStrongCount = Object.values(initialStatuses).filter((status) => status === "strong").length;
  const next = { ...snapshot, initialStatuses, initialStrongCount: Math.min(initialStrongCount, totalWords) };
  if (Object.keys(initialStatuses).length > Object.keys(snapshot.initialStatuses).length) {
    saveLessonProgressSnapshot(studentScope, lessonId, next);
  }
  return next;
}

export function buildLessonVocabularyProgress({
  lessonId,
  entries,
  attempts,
  mastery,
  priorityReviewWords = [],
  studentScope,
  currentAttempt,
}: {
  lessonId: string;
  entries: VocabQuizEntry[];
  attempts: VocabQuizAttempt[];
  mastery: VocabPriorityReviewWord[];
  priorityReviewWords?: VocabPriorityReviewWord[];
  studentScope?: string;
  currentAttempt?: VocabQuizSummary;
}): LessonVocabularyProgress {
  const uniqueEntries = entries.filter((entry, index, all) => entryId(entry) && all.findIndex((candidate) => entryId(candidate) === entryId(entry)) === index);
  const totalWords = uniqueEntries.length;
  const allAttempts = mergeCurrentAttempt(attempts, currentAttempt);
  const knowItAttempt = latestAttempt(allAttempts, "tier1");
  const sayItAttempt = latestAttempt(allAttempts, "tier2");
  const useItAttempt = latestAttempt(allAttempts, "tier3");
  const diagnosticComplete = Boolean(knowItAttempt && sayItAttempt && useItAttempt);
  const snapshot = loadLessonProgressSnapshot(studentScope, lessonId);
  const statuses = currentStatuses(uniqueEntries, mastery);
  const nextSnapshot = recordInitialStatuses(snapshot, statuses, diagnosticComplete, totalWords, studentScope, lessonId);
  const strongWords = uniqueEntries.filter((entry) => statuses.get(entryId(entry)) === "strong").length;
  const focusWords = priorityReviewWords.length > 0
    ? priorityReviewWords
    : mastery.filter((word) => word.status !== "MASTERED");
  const personalizedAttempts = allAttempts.filter((attempt) => attempt.mode === "weak_words");
  const improved = uniqueEntries
    .map((entry): VocabularyImprovement | null => {
      const id = entryId(entry);
      const initialStatus = nextSnapshot.initialStatuses[id];
      const finalStatus = statuses.get(id) || "needs_practice";
      if (!initialStatus) return null;
      const answeredInPersonalizedPractice = personalizedAttempts.some((attempt) =>
        attempt.questionResults?.some((result) => entryId({ wordId: result.conceptId, word: result.word }) === id),
      );
      return {
        wordId: entry.wordId || id,
        targetWord: entry.word,
        initialStatus,
        finalStatus,
        strengthenedThroughPractice: initialStatus !== "strong" && finalStatus === "strong" && answeredInPersonalizedPractice,
      };
    })
    .filter((value): value is VocabularyImprovement => Boolean(value));
  const strengthenedCount = improved.filter((item) => item.strengthenedThroughPractice).length;
  const required = Math.max(0, totalWords - (nextSnapshot.initialStrongCount ?? 0));
  const strengthenRemaining = focusWords.length > 0 ? focusWords.length : Math.max(0, totalWords - strongWords);
  const strengthenCompleted = required === 0 || (diagnosticComplete && strengthenRemaining === 0);
  const challengeAttempts = allAttempts.filter((attempt) => attempt.mode === "challenge");
  const scores = challengeAttempts.map((attempt) => ({ score: attempt.correctCount, total: attempt.totalQuestions }));
  const bestScore = scores.length ? Math.max(...scores.map((score) => score.score)) : nextSnapshot.challengeBestScore;
  const lastChallenge = challengeAttempts.sort((a, b) => new Date(b.completedAt).getTime() - new Date(a.completedAt).getTime())[0];
  const knowIt = roundFromAttempt(knowItAttempt);
  const sayIt = roundFromAttempt(sayItAttempt);
  const useIt = roundFromAttempt(useItAttempt);
  return {
    lessonId,
    totalWords,
    strongWords,
    remainingWords: Math.max(0, totalWords - strongWords),
    vocabularyReviewCompleted: Boolean(knowItAttempt || sayItAttempt || useItAttempt),
    knowIt,
    sayIt,
    useIt,
    strengthen: {
      required,
      strengthened: strengthenedCount,
      remaining: Math.max(0, strengthenRemaining),
      completed: strengthenCompleted,
    },
    lessonCompleted: diagnosticComplete && strengthenCompleted,
    challenge: {
      available: diagnosticComplete,
      attempts: challengeAttempts.length,
      lastScore: lastChallenge?.correctCount,
      bestScore,
    },
    initialStrongCount: nextSnapshot.initialStrongCount ?? 0,
    strengthenedCount,
    improvements: improved,
    focusWords,
  };
}

export function nextLearningStage(progress: LessonVocabularyProgress): "knowIt" | "sayIt" | "useIt" | "strengthen" | "complete" {
  if (!progress.knowIt.completed) return "knowIt";
  if (!progress.sayIt.completed) return "sayIt";
  if (!progress.useIt.completed) return "useIt";
  if (!progress.strengthen.completed) return "strengthen";
  return "complete";
}

export function statusLabel(status: LearnerVocabularyStatus): string {
  return STATUS_ORDER.includes(status) ? status : "needs_practice";
}
