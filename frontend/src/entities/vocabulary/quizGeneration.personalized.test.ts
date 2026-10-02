import { describe, expect, it } from "vitest";
import { buildPersonalizedAssessmentQuestions } from "./quizGeneration";
import type { VocabAssessmentQuestion, VocabQuizEntry } from "./types";

function question(
  questionId: string,
  questionType: "basic_meaning_mcq" | "character_to_pinyin_typing" | "context_cloze_mcq",
  level: "easy" | "medium" | "hard",
): VocabAssessmentQuestion {
  return {
    questionId,
    wordId: "word-1",
    targetWord: "學習",
    pinyin: "xuéxí",
    pos: "V",
    simpleEnglishMeaning: "study",
    level,
    difficultyWeight: level === "easy" ? 1 : level === "medium" ? 2 : 3,
    questionType,
    answerFormat: questionType === "character_to_pinyin_typing" ? "free_text" : "single_choice",
    prompt: questionId,
    options: questionType === "character_to_pinyin_typing" ? [] : ["學習", "休息"],
    correctAnswer: questionType === "character_to_pinyin_typing" ? "xuéxí" : "學習",
    acceptedAnswers: [questionType === "character_to_pinyin_typing" ? "xuéxí" : "學習"],
    explanation: "",
  };
}

// Deliberately NOT in dimension order, so selection cannot be "first bank item".
const bank = [
  question("context", "context_cloze_mcq", "hard"),
  question("pinyin", "character_to_pinyin_typing", "medium"),
  question("meaning", "basic_meaning_mcq", "easy"),
];

const ALL_SEEN = ["basic_meaning_mcq", "character_to_pinyin_typing", "context_cloze_mcq"];

function entry(overrides: Partial<VocabQuizEntry> = {}): VocabQuizEntry {
  return { word: "學習", translation: "study", wordId: "word-1", assessmentQuestions: bank, ...overrides };
}

const pick = (value: VocabQuizEntry) => buildPersonalizedAssessmentQuestions([value])[0].assessment.questionId;

describe("personalized practice selection follows the server's current dimension", () => {
  it("Case B: a single unresolved dimension is the one practiced", () => {
    expect(pick(entry({ bktNextDimension: "meaning", bktSeenQuestionKinds: ALL_SEEN }))).toBe("meaning");
  });

  it("Case C: with several unresolved dimensions it practices whichever the server names, deterministically", () => {
    expect(pick(entry({ bktNextDimension: "meaning", bktSeenQuestionKinds: ALL_SEEN }))).toBe("meaning");
    // Meaning is repaired server-side; pinyin is still unresolved -> pinyin, not meaning again.
    expect(pick(entry({ bktNextDimension: "pinyin", bktSeenQuestionKinds: ALL_SEEN }))).toBe("pinyin");
  });

  it("Case D: an old incorrect response in history never pulls selection back to a repaired dimension", () => {
    // Meaning was failed long ago (it is in the seen history), has since been
    // repaired; the server now targets pinyin, so meaning must not come back.
    expect(pick(entry({ bktNextDimension: "pinyin", bktSeenQuestionKinds: ALL_SEEN, bktObservationCount: 9 }))).toBe("pinyin");
  });

  it("selects the same item every time (no randomness in the choice itself)", () => {
    const picks = Array.from({ length: 25 }, () => pick(entry({ bktNextDimension: "pinyin" })));
    expect(new Set(picks)).toEqual(new Set(["pinyin"]));
  });

  it("builds exactly one question per word and keeps the server's word order", () => {
    const a = entry({ wordId: "a", bktNextDimension: "pinyin" });
    const b = entry({ wordId: "b", bktNextDimension: "context" });

    const built = buildPersonalizedAssessmentQuestions([b, a]);

    expect(built.map((item) => item.assessment.questionId)).toEqual(["context", "pinyin"]);
  });

  it("without a server dimension, falls back to the first unseen dimension in stable order, never to history of failures", () => {
    expect(pick(entry({ bktSeenQuestionKinds: ["basic_meaning_mcq"] }))).toBe("pinyin");
    expect(pick(entry({ bktSeenQuestionKinds: ["basic_meaning_mcq", "character_to_pinyin_typing"] }))).toBe("context");
    expect(pick(entry({}))).toBe("meaning");
  });

  it("falls back to a stable item when the targeted dimension has no published question", () => {
    const meaningOnly = entry({ assessmentQuestions: [bank[2]], bktNextDimension: "pinyin" });

    expect(pick(meaningOnly)).toBe("meaning");
  });
});
