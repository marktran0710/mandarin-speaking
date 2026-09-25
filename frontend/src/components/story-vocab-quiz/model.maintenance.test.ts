import { describe, expect, it } from "vitest";
import { buildMaintenanceAssessmentQuestions, type VocabQuizEntry } from "@entities/vocabulary";

function question(
  questionId: string,
  questionType: "basic_meaning_mcq" | "character_to_pinyin_typing" | "context_cloze_mcq",
  level: "easy" | "medium" | "hard",
): NonNullable<VocabQuizEntry["assessmentQuestions"]>[number] {
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

const bank = [
  question("meaning", "basic_meaning_mcq", "easy"),
  question("pinyin", "character_to_pinyin_typing", "medium"),
  question("context", "context_cloze_mcq", "hard"),
];

describe("maintenance assessment selection", () => {
  it("rotates across dimensions instead of repeatedly selecting the first bank item", () => {
    const base: VocabQuizEntry = {
      word: "學習",
      translation: "study",
      wordId: "word-1",
      assessmentQuestions: bank,
      bktSeenQuestionKinds: ["basic_meaning_mcq", "character_to_pinyin_typing", "context_cloze_mcq"],
    };

    expect(buildMaintenanceAssessmentQuestions([{ ...base, bktObservationCount: 3 }])[0].assessment.questionId).toBe("meaning");
    expect(buildMaintenanceAssessmentQuestions([{ ...base, bktObservationCount: 4 }])[0].assessment.questionId).toBe("pinyin");
    expect(buildMaintenanceAssessmentQuestions([{ ...base, bktObservationCount: 5 }])[0].assessment.questionId).toBe("context");
  });

  it("prefers a dimension that has not appeared in the server evidence yet", () => {
    const entry: VocabQuizEntry = {
      word: "學習",
      translation: "study",
      wordId: "word-1",
      assessmentQuestions: bank,
      bktSeenQuestionKinds: ["basic_meaning_mcq"],
      bktObservationCount: 1,
    };

    expect(buildMaintenanceAssessmentQuestions([entry])[0].assessment.questionId).toBe("pinyin");
  });
});
