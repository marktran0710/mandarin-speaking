import { beforeEach, describe, expect, it } from "vitest";
import {
  buildLessonVocabularyProgress,
  nextLearningStage,
  saveLessonProgressSnapshot,
} from "./lesson-vocab-progress";
import type { VocabPriorityReviewWord, VocabQuizAttempt } from "../../services/api/quiz-analytics";

const entries = [
  { wordId: "w1", word: "錢包", translation: "wallet" },
  { wordId: "w2", word: "有空", translation: "free" },
  { wordId: "w3", word: "哪裡", translation: "where" },
];

function mastery(statuses: Array<VocabPriorityReviewWord["status"]>): VocabPriorityReviewWord[] {
  return statuses.map((status, index) => ({
    wordId: `w${index + 1}`,
    word: entries[index].word,
    meaning: entries[index].translation,
    pLearned: status === "STRONG" ? 0.98 : 0.3,
    status,
    observationCount: 3,
    correctCount: status === "STRONG" ? 3 : 1,
    incorrectCount: status === "STRONG" ? 0 : 2,
  }));
}

function attempt(mode: VocabQuizAttempt["mode"], correctCount: number): VocabQuizAttempt {
  return {
    id: `${mode}-${correctCount}`,
    storyId: "lesson-5",
    studentName: "Student",
    mode,
    completedAt: `2026-09-0${correctCount}T00:00:00Z`,
    totalQuestions: 3,
    correctCount,
    totalTimeMs: 1000,
    questionResults: entries.map((entry, index) => ({ word: entry.word, conceptId: entry.wordId, correct: index < correctCount, timeMs: 100 })),
  };
}

function roundPresence(tier1: boolean, tier2: boolean, tier3: boolean) {
  return {
    tier1: { level: "tier1" as const, roundType: "know_it" as const, observedWords: 3, observations: 3, complete: tier1 },
    tier2: { level: "tier2" as const, roundType: "say_it" as const, observedWords: 3, observations: 3, complete: tier2 },
    tier3: { level: "tier3" as const, roundType: "use_it" as const, observedWords: 3, observations: 3, complete: tier3 },
  };
}

describe("lesson vocabulary progress", () => {
  beforeEach(() => localStorage.clear());

  it("calculates strong words and round accuracy from stored observations", () => {
    const progress = buildLessonVocabularyProgress({
      lessonId: "lesson-5",
      entries,
      mastery: mastery(["STRONG", "PROVISIONAL_REVIEW", "NEEDS_PRACTICE"]),
      attempts: [attempt("tier1", 2), attempt("tier2", 1), attempt("tier3", 3)],
      priorityReviewWords: mastery(["PROVISIONAL_REVIEW", "NEEDS_PRACTICE"]),
      diagnosticComplete: true,
      studentScope: "student-1",
    });

    expect(progress.strongWords).toBe(1);
    expect(progress.remainingWords).toBe(2);
    expect(progress.knowIt).toMatchObject({ completed: true, correct: 2, accuracy: 67 });
    expect(progress.sayIt).toMatchObject({ completed: true, correct: 1, accuracy: 33 });
    expect(progress.useIt).toMatchObject({ completed: true, correct: 3, accuracy: 100 });
    expect(nextLearningStage(progress)).toBe("strengthen");
  });

  it("preserves the first diagnostic state and identifies words strengthened in review", () => {
    saveLessonProgressSnapshot("student-1", "lesson-5", {
      initialStatuses: { w1: "strong", w2: "needs_practice", w3: "needs_practice" },
      initialStrongCount: 1,
    });
    const progress = buildLessonVocabularyProgress({
      lessonId: "lesson-5",
      entries,
      mastery: mastery(["STRONG", "STRONG", "NEEDS_PRACTICE"]),
      attempts: [
        attempt("tier1", 2), attempt("tier2", 2), attempt("tier3", 2),
        { ...attempt("weak_words", 2), id: "strengthen-w2" },
      ],
      priorityReviewWords: mastery(["NEEDS_PRACTICE"]),
      diagnosticComplete: true,
      studentScope: "student-1",
    });

    expect(progress.initialStrongCount).toBe(1);
    expect(progress.strengthenedCount).toBe(1);
    expect(progress.improvements.find((item) => item.wordId === "w2")).toMatchObject({
      initialStatus: "needs_practice",
      finalStatus: "strong",
      strengthenedThroughPractice: true,
    });
  });

  it("does not advance from a locally stored attempt when the server round is incomplete", () => {
    const progress = buildLessonVocabularyProgress({
      lessonId: "lesson-5",
      entries,
      mastery: mastery(["NEEDS_PRACTICE", "NEEDS_PRACTICE", "NEEDS_PRACTICE"]),
      attempts: [attempt("tier1", 3)],
      diagnosticComplete: false,
      roundPresence: roundPresence(false, false, false),
      studentScope: "student-1",
    });

    expect(progress.knowIt.completed).toBe(false);
    expect(nextLearningStage(progress)).toBe("knowIt");
  });

  it("advances to the next round only after server round completion", () => {
    const progress = buildLessonVocabularyProgress({
      lessonId: "lesson-5",
      entries,
      mastery: mastery(["NEEDS_PRACTICE", "NEEDS_PRACTICE", "NEEDS_PRACTICE"]),
      attempts: [attempt("tier1", 3), attempt("tier2", 3)],
      diagnosticComplete: false,
      roundPresence: roundPresence(true, false, false),
      studentScope: "student-1",
    });

    expect(progress.knowIt.completed).toBe(true);
    expect(progress.sayIt.completed).toBe(false);
    expect(nextLearningStage(progress)).toBe("sayIt");
  });

  it("keeps challenge mode optional and tracks its best score", () => {
    const progress = buildLessonVocabularyProgress({
      lessonId: "lesson-5",
      entries,
      mastery: mastery(["STRONG", "STRONG", "STRONG"]),
      attempts: [attempt("tier1", 3), attempt("tier2", 3), attempt("tier3", 3), attempt("challenge", 2), attempt("challenge", 3)],
      diagnosticComplete: true,
      studentScope: "student-1",
    });

    expect(progress.lessonCompleted).toBe(true);
    expect(progress.challenge).toMatchObject({ available: true, attempts: 2, bestScore: 3, lastScore: 3 });
    expect(nextLearningStage(progress)).toBe("complete");
  });
});
