import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StoryVocabQuiz from "./StoryVocabQuiz";

vi.mock("../../services/database", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../services/database")>();
  return {
    ...actual,
    canUseDatabase: vi.fn(() => false),
  };
});

afterEach(() => vi.restoreAllMocks());

describe("CSV vocabulary assessment flow", () => {
  it("runs the complete Easy → Medium → Hard assessment in order", async () => {
    const user = userEvent.setup();
    const onComplete = vi.fn();
    const entries = [{
      word: "哪裡 / 哪兒",
      translation: "where",
      wordId: "MC1_003",
      pinyin: "nǎlǐ / nǎr",
      pos: "N",
      bktValidationStatus: "APPROVED" as const,
      assessmentQuestions: [
        {
          questionId: "MC1_003_EASY", wordId: "MC1_003", targetWord: "哪裡 / 哪兒",
          pinyin: "nǎlǐ / nǎr", pos: "N", simpleEnglishMeaning: "where", level: "easy" as const,
          difficultyWeight: 1 as const, questionType: "basic_meaning_mcq" as const,
          answerFormat: "single_choice" as const, prompt: "Which Chinese word means “where”?",
          options: ["哪裡 / 哪兒", "那裡 / 那兒", "這裡 / 這兒", "有空"], correctAnswer: "哪裡 / 哪兒",
          acceptedAnswers: ["哪裡 / 哪兒"], explanation: "哪裡 or 哪兒 means where.",
        },
        {
          questionId: "MC1_003_MEDIUM", wordId: "MC1_003", targetWord: "哪裡 / 哪兒",
          pinyin: "nǎlǐ / nǎr", pos: "N", simpleEnglishMeaning: "where", level: "medium" as const,
          difficultyWeight: 2 as const, questionType: "context_cloze_mcq" as const,
          answerFormat: "single_choice" as const, prompt: "我的錢包在____？ (Where is my wallet?)",
          options: ["哪裡", "那裡", "這裡", "半"], correctAnswer: "哪裡",
          acceptedAnswers: ["哪裡"], explanation: "哪裡 asks about an unknown place.",
        },
        {
          questionId: "MC1_003_HARD", wordId: "MC1_003", targetWord: "哪裡 / 哪兒",
          pinyin: "nǎlǐ / nǎr", pos: "N", simpleEnglishMeaning: "where", level: "hard" as const,
          difficultyWeight: 3 as const, questionType: "productive_recall" as const,
          answerFormat: "free_text" as const, prompt: "我的錢包在____？\nWhere is my wallet?",
          options: [], correctAnswer: "哪裡", acceptedAnswers: ["哪裡", "哪兒"],
          explanation: "Both 哪裡 and 哪兒 are accepted for where.",
        },
      ],
    }];

    render(<StoryVocabQuiz entries={entries} onDone={vi.fn()} onComplete={onComplete} />);
    await user.click(screen.getByRole("button", { name: /Full assessment/ }));
    await user.click(screen.getByRole("button", { name: "哪裡 / 哪兒" }));
    await user.click(screen.getByRole("button", { name: /Next question/ }));
    await user.click(screen.getByRole("button", { name: "哪裡" }));
    await user.click(screen.getByRole("button", { name: /Next question/ }));

    await user.type(screen.getByRole("textbox", { name: "Your answer" }), " 哪 兒？ ");
    await user.click(screen.getByRole("button", { name: /Check answer/ }));
    expect(screen.getByText("Correct!")).toBeInTheDocument();
    expect(screen.getByText(/Both 哪裡 and 哪兒 are accepted/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /See results/ }));
    await user.click(screen.getByRole("button", { name: /Continue to practice/ }));

    expect(onComplete).toHaveBeenCalledTimes(3);
    const results = onComplete.mock.calls.map(([summary]) => summary.questionResults[0]);
    expect(results.map((result) => result.level)).toEqual(["easy", "medium", "hard"]);
    expect(results.map((result) => result.itemId)).toEqual([
      "MC1_003_EASY", "MC1_003_MEDIUM", "MC1_003_HARD",
    ]);
    expect(results.every((result) => result.timeMs >= 0)).toBe(true);
  });
});
