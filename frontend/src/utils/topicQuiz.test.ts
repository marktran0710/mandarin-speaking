import { describe, expect, it } from "vitest";
import { topicHasQuiz, topicQuizEntries } from "./topicQuiz";

const question = (overrides: Record<string, unknown> = {}) => ({
  questionId: "bed-easy",
  wordId: "bed-1",
  targetWord: "bed",
  pinyin: "chuang",
  pos: "N",
  simpleEnglishMeaning: "bed",
  level: "easy" as const,
  difficultyWeight: 1 as const,
  questionType: "basic_meaning_mcq" as const,
  answerFormat: "single_choice" as const,
  prompt: "What does bed mean?",
  options: ["bed", "book"],
  correctAnswer: "bed",
  acceptedAnswers: ["bed"],
  explanation: "",
  ...overrides,
});

describe("canonical topic quiz source", () => {
  it("returns no quiz when vocab_assessment is absent", () => {
    expect(topicQuizEntries({})).toEqual([]);
    expect(topicHasQuiz({})).toBe(false);
  });

  it("groups canonical assessment questions by stable word id", () => {
    const entries = topicQuizEntries({ vocabAssessment: [question(), question({
      questionId: "bed-hard",
      level: "hard",
      questionType: "productive_recall",
      answerFormat: "free_text",
      options: [],
      correctAnswer: "bed",
    })] });
    expect(entries).toHaveLength(1);
    expect(entries[0].wordId).toBe("bed-1");
    expect(entries[0].assessmentQuestions).toHaveLength(2);
    expect(entries[0].bktValidationStatus).toBe("APPROVED");
  });

  it("normalizes backend level casing and retains authored context prompts", () => {
    const entries = topicQuizEntries({ vocabAssessment: [question({
      level: "Easy",
      questionType: "context_cloze_mcq",
      prompt: "I sleep on a bed.",
    } as never)] });
    expect(entries[0].assessmentQuestions?.[0].level).toBe("easy");
    expect(entries[0].lessonSentences).toEqual(["I sleep on a bed."]);
  });

  it("ignores malformed or unsupported assessment items", () => {
    const entries = topicQuizEntries({ vocabAssessment: [
      question(),
      { ...question(), wordId: "", questionId: "bad" },
      { ...question(), level: "unknown" as never, questionId: "bad-level" },
    ] });
    expect(entries.map((entry) => entry.wordId)).toEqual(["bed-1"]);
  });
});
