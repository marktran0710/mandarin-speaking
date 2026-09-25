import { describe, expect, it } from "vitest";
import { buildDiagnosticRoundQuestions, validateRoundCoverage, type VocabQuizEntry } from "@entities/vocabulary";

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

  it("keeps rounds 1/3 as four-choice and round 2 as a typed response", () => {
    const knowIt = buildDiagnosticRoundQuestions(entries, "tier1");
    const sayIt = buildDiagnosticRoundQuestions(entries, "tier2");
    const useIt = buildDiagnosticRoundQuestions(entries, "tier3");
    expect(knowIt.every((question) => question.options.length === 4)).toBe(true);
    expect(sayIt.every((question) => question.answerFormat === "free_text" && question.options.length === 0)).toBe(true);
    expect(useIt.every((question) => question.answerFormat === "single_choice" && question.options.length === 4)).toBe(true);
    // No Chinese IME required for Round 3 — every option offered is a whole
    // word (a real distractor or filler), and the correct answer is among them.
    expect(useIt.every((question) => new Set(question.options).size === 4 && question.options.includes(question.correctAnswer))).toBe(true);
  });

  it("prefers the bank's teacher-approved medium-level MCQ options for Round 3", () => {
    const entry: VocabQuizEntry = {
      word: "巧克力",
      translation: "chocolate",
      wordId: "lesson-5-chocolate",
      pinyin: "qiǎokèlì",
      assessmentQuestions: [
        {
          questionId: "lesson-5-chocolate-medium",
          wordId: "lesson-5-chocolate",
          targetWord: "巧克力",
          pinyin: "qiǎokèlì",
          pos: "N",
          simpleEnglishMeaning: "chocolate",
          level: "medium",
          difficultyWeight: 2,
          questionType: "context_cloze_mcq",
          answerFormat: "single_choice",
          prompt: "我喜歡吃____蛋糕。",
          options: ["巧克力", "牛奶", "麵包", "蘋果"],
          correctAnswer: "巧克力",
          acceptedAnswers: ["巧克力"],
          explanation: "Chocolate cake uses 巧克力.",
        },
        {
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
        },
      ],
    };

    const question = buildDiagnosticRoundQuestions([entry], "tier3")[0];

    expect(question.answerFormat).toBe("single_choice");
    expect(question.correctAnswer).toBe("巧克力");
    expect(new Set(question.options)).toEqual(new Set(["巧克力", "牛奶", "麵包", "蘋果"]));
  });

  it("uses the workbook's hard-level context MCQ when the bank stores Round 3 there", () => {
    const entry: VocabQuizEntry = {
      word: "房間",
      translation: "room",
      wordId: "C5-5-2-I3-W003",
      pinyin: "fángjiān",
      assessmentQuestions: [{
        questionId: "C5-5-2-I3-W003_HARD",
        wordId: "C5-5-2-I3-W003",
        targetWord: "房間",
        pinyin: "fángjiān",
        pos: "N",
        simpleEnglishMeaning: "room",
        level: "hard",
        difficultyWeight: 3,
        questionType: "context_cloze_mcq",
        answerFormat: "single_choice",
        prompt: "Choose the correct word: 我的____不太大。",
        options: ["房間", "房子", "客廳", "廚房"],
        correctAnswer: "房間",
        acceptedAnswers: ["房間"],
        explanation: "Correct answer: 房間.",
      }],
    };

    const question = buildDiagnosticRoundQuestions([entry], "tier3")[0];

    expect(question.prompt).toBe("Choose the correct word: 我的____不太大。");
    expect(question.correctAnswer).toBe("房間");
    expect(new Set(question.options)).toEqual(new Set(["房間", "房子", "客廳", "廚房"]));
  });

  it("keeps workbook pinyin variants for optional-form words", () => {
    const entry: VocabQuizEntry = {
      word: "電視(機)",
      translation: "TV (television)",
      wordId: "C5-5-3-I2-W044",
      pinyin: "diànshì(jī)",
      assessmentQuestions: [{
        questionId: "C5-5-3-I2-W044_MEDIUM",
        wordId: "C5-5-3-I2-W044",
        targetWord: "電視(機)",
        pinyin: "diànshì(jī)",
        pos: "N",
        simpleEnglishMeaning: "TV (television)",
        level: "medium",
        difficultyWeight: 2,
        questionType: "character_to_pinyin_typing",
        answerFormat: "free_text",
        prompt: "Type the pinyin for 「電視(機)」.",
        options: [],
        correctAnswer: "diànshì(jī)",
        acceptedAnswers: ["diànshì(jī)", "diànshìjī", "diànshì"],
        explanation: "The pinyin for 電視(機) is diànshì(jī).",
      }],
    };

    const question = buildDiagnosticRoundQuestions([entry], "tier2")[0];

    expect(question.acceptedAnswers).toEqual(["diànshì(jī)", "diànshìjī", "diànshì"]);
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
    // No medium-level MCQ or other lesson words to draw from — filler pads
    // the options, but the real answer is still always one of them.
    expect(question.options).toHaveLength(4);
    expect(question.options).toContain("巧克力");
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
