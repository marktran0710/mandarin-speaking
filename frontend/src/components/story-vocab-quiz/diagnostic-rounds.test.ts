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

  it("uses an approved lesson sentence for Round 3 before an assessment-bank fallback prompt", () => {
    const entry: VocabQuizEntry = {
      word: "巧克力",
      translation: "chocolate",
      wordId: "lesson-5-chocolate",
      pinyin: "qiǎokèlì",
      lessonSentences: ["我喜歡巧克力蛋糕。"],
      assessmentQuestions: [{
        questionId: "lesson-5-chocolate-hard",
        wordId: "lesson-5-chocolate",
        targetWord: "巧克力",
        pinyin: "qiǎokèlì",
        pos: "N",
        simpleEnglishMeaning: "chocolate",
        level: "hard",
        difficultyWeight: 3,
        questionType: "productive_recall",
        answerFormat: "free_text",
        prompt: "Generated fallback context.",
        options: [],
        correctAnswer: "巧克力",
        acceptedAnswers: ["巧克力"],
        explanation: "Chocolate is 巧克力.",
      }],
    };

    const question = buildDiagnosticRoundQuestions([entry], "tier3")[0];

    expect(question.prompt).toBe("Complete the sentence: 我喜歡____蛋糕。");
    expect(question.correctAnswer).toBe("巧克力");
  });

  it("keeps the assessment-bank prompt when lesson sentences omit or repeat the target", () => {
    const entry: VocabQuizEntry = {
      word: "巧克力",
      translation: "chocolate",
      wordId: "lesson-5-chocolate",
      lessonSentences: ["這個蛋糕很好吃。", "巧克力和巧克力蛋糕都很好吃。"],
      assessmentQuestions: [{
        questionId: "lesson-5-chocolate-hard",
        wordId: "lesson-5-chocolate",
        targetWord: "巧克力",
        pinyin: "qiǎokèlì",
        pos: "N",
        simpleEnglishMeaning: "chocolate",
        level: "hard",
        difficultyWeight: 3,
        questionType: "productive_recall",
        answerFormat: "free_text",
        prompt: "Generated fallback context.",
        options: [],
        correctAnswer: "巧克力",
        acceptedAnswers: ["巧克力"],
        explanation: "Chocolate is 巧克力.",
      }],
    };

    expect(buildDiagnosticRoundQuestions([entry], "tier3")[0].prompt).toBe("Generated fallback context.");
  });

  it("reports missing and duplicate coverage before a round can start", () => {
    const questions = buildDiagnosticRoundQuestions(entries, "tier1");
    const invalid = validateRoundCoverage({ lessonVocabulary: entries, roundQuestions: [...questions.slice(1), questions[1]] });
    expect(invalid.valid).toBe(false);
    expect(invalid.errors.some((error) => error.startsWith("MISSING_WORD "))).toBe(true);
    expect(invalid.errors.some((error) => error.startsWith("DUPLICATE_WORD "))).toBe(true);
  });
});
