import { describe, expect, it } from "vitest";
import { buildQuizQuestion } from "./quizSession";
import type { VocabQuizEntry } from "./types";

// Legacy (no published assessment bank) weak-word questions must target the
// same server-chosen dimension as the assessment-bank selector.
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

describe("legacy weak-word question kind follows the server's next dimension", () => {
  const pool = [make("學習"), make("休息"), make("工作"), make("看書")];

  it("pinyin dimension -> only pinyin questions", () => {
    expect(kindsFor(make("學習", { bktNextDimension: "pinyin", bktSeenQuestionKinds: ["pinyin", "cloze", "translation"] }), pool)).toEqual(new Set(["pinyin"]));
  });

  it("context dimension -> only cloze questions", () => {
    expect(kindsFor(make("學習", { bktNextDimension: "context", bktSeenQuestionKinds: ["pinyin", "cloze", "translation"] }), pool)).toEqual(new Set(["cloze"]));
  });

  it("meaning dimension -> only meaning-type questions (translation / reverse)", () => {
    const kinds = kindsFor(make("學習", { bktNextDimension: "meaning", bktSeenQuestionKinds: ["pinyin", "cloze", "translation"] }), pool);
    expect([...kinds].every((kind) => kind === "translation" || kind === "reverse")).toBe(true);
  });
});
