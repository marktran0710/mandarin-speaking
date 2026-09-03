import { describe, expect, it } from "vitest";
import { buildDiagnosticRoundQuestions, validateRoundCoverage, type VocabQuizEntry } from "./model";

const entries: VocabQuizEntry[] = Array.from({ length: 15 }, (_, index) => ({
  word: `詞${index + 1}`,
  translation: `meaning ${index + 1}`,
  wordId: `word-${index + 1}`,
  pinyin: `ci${index + 1}`,
  bktValidationStatus: "APPROVED",
}));

describe("dynamic diagnostic rounds", () => {
  it("creates 15 questions per round with one stable concept and distinct exposure ids", () => {
    const rounds = (["tier1", "tier2", "tier3"] as const).map((mode) => buildDiagnosticRoundQuestions(entries, mode));
    expect(rounds).toHaveLength(3);
    rounds.forEach((questions, index) => {
      expect(questions).toHaveLength(15);
      expect(validateRoundCoverage({ lessonVocabulary: entries, roundQuestions: questions })).toEqual({ valid: true, errors: [] });
      expect(new Set(questions.map((question) => question.wordId)).size).toBe(15);
      expect(questions.every((question) => question.level === (["easy", "medium", "hard"] as const)[index])).toBe(true);
    });
    const questionIds = rounds.flat().map((question) => question.questionId);
    expect(new Set(questionIds).size).toBe(45);
    const byWord = new Map<string, string[]>();
    rounds.flat().forEach((question) => byWord.set(question.wordId, [...(byWord.get(question.wordId) ?? []), question.questionId]));
    expect([...byWord.values()].every((ids) => ids.length === 3 && new Set(ids).size === 3)).toBe(true);
  });

  it("keeps round 1 as four-choice and rounds 2/3 as typed responses", () => {
    const knowIt = buildDiagnosticRoundQuestions(entries, "tier1");
    const sayIt = buildDiagnosticRoundQuestions(entries, "tier2");
    const useIt = buildDiagnosticRoundQuestions(entries, "tier3");
    expect(knowIt.every((question) => question.options.length === 4)).toBe(true);
    expect(sayIt.every((question) => question.answerFormat === "free_text" && question.options.length === 0)).toBe(true);
    expect(useIt.every((question) => question.answerFormat === "free_text" && question.options.length === 0)).toBe(true);
  });

  it("reports missing and duplicate coverage before a round can start", () => {
    const questions = buildDiagnosticRoundQuestions(entries, "tier1");
    const invalid = validateRoundCoverage({ lessonVocabulary: entries, roundQuestions: [...questions.slice(1), questions[1]] });
    expect(invalid.valid).toBe(false);
    expect(invalid.errors.some((error) => error.startsWith("MISSING_WORD "))).toBe(true);
    expect(invalid.errors.some((error) => error.startsWith("DUPLICATE_WORD "))).toBe(true);
  });
});
