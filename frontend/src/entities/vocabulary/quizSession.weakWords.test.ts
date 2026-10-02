import { describe, expect, it } from "vitest";
import { buildQuizQuestion } from "./quizSession";
import { MissingPracticeAssessmentError } from "./quizGeneration";
import type { VocabQuizEntry } from "./types";

// A legacy question is not a substitute for a missing published target item.
const clozeSentence = "我每天學習中文。";
const make = (word: string, overrides: Partial<VocabQuizEntry> = {}): VocabQuizEntry => ({
  word,
  translation: `meaning of ${word}`,
  pinyin: "xuéxí",
  pos: "V",
  aiCloze: [{ sentence: clozeSentence.replace("學習", word), distractors: ["休息", "工作", "看書"] }],
  ...overrides,
});
const kindsFor = (target: VocabQuizEntry, pool: VocabQuizEntry[]) => new Set(
  Array.from({ length: 40 }, () => buildQuizQuestion(target, pool, "weak_words", {
    distractorEntries: pool, excludedKinds: new Set(), forbiddenAnswers: new Set(),
  })?.kind),
);

describe("targeted weak-word practice requires a published item", () => {
  const pool = [make("學習"), make("休息"), make("工作"), make("看書")];

  it.each(["meaning", "pinyin", "context"] as const)("rejects a legacy bankless %s target", (bktNextDimension) => {
    expect(() => kindsFor(make("學習", { bktNextDimension }), pool)).toThrow(MissingPracticeAssessmentError);
  });
});
