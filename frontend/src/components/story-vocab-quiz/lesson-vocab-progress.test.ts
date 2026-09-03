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
    pLearned: status === "MASTERED" ? 0.98 : 0.3,
    status,
    observationCount: 3,
    correctCount: status === "MASTERED" ? 3 : 1,
    incorrectCount: status === "MASTERED" ? 0 : 2,
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

describe("lesson vocabulary progress", () => {
  beforeEach(() => localStorage.clear());

  it("calculates strong words and round accuracy from stored observations", () => {
    const progress = buildLessonVocabularyProgress({
      lessonId: "lesson-5",
      entries,
      mastery: mastery(["MASTERED", "DEVELOPING", "NEEDS_REVIEW"]),
      attempts: [attempt("tier1", 2), attempt("tier2", 1), attempt("tier3", 3)],
      priorityReviewWords: mastery(["DEVELOPING", "NEEDS_REVIEW"]),
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
      mastery: mastery(["MASTERED", "MASTERED", "NEEDS_REVIEW"]),
      attempts: [
        attempt("tier1", 2), attempt("tier2", 2), attempt("tier3", 2),
        { ...attempt("weak_words", 1), id: "strengthen-w2" },
      ],
      priorityReviewWords: mastery(["NEEDS_REVIEW"]),
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

  it("keeps challenge mode optional and tracks its best score", () => {
    const progress = buildLessonVocabularyProgress({
      lessonId: "lesson-5",
      entries,
      mastery: mastery(["MASTERED", "MASTERED", "MASTERED"]),
      attempts: [attempt("tier1", 3), attempt("tier2", 3), attempt("tier3", 3), attempt("challenge", 2), attempt("challenge", 3)],
      studentScope: "student-1",
    });

    expect(progress.lessonCompleted).toBe(true);
    expect(progress.challenge).toMatchObject({ available: true, attempts: 2, bestScore: 3, lastScore: 3 });
    expect(nextLearningStage(progress)).toBe("complete");
  });
});
