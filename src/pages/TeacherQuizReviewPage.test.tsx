import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TeacherQuizReviewPage from "./TeacherQuizReviewPage";

const story = {
  id: "s1",
  title: "測試故事",
  learningGoal: "goal",
  published: true,
  frames: [
    {
      imageUrl: "u",
      prompt: "p",
      vocabulary: "知道,一起",
      vocabularyPinyin: "zhīdào,yìqǐ",
      vocabularyTranslation: "to know,together",
      vocabularySynonym: JSON.stringify([
        [{ synonym: "曉得", distractors: ["不懂"] }],
        [{ synonym: "共同", distractors: ["分開"] }],
      ]),
    },
  ],
  quizExclusions: [{ word: "一起", kind: "synonym", index: 0 }],
};

vi.mock("../services/database", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/database")>();
  return {
    ...actual,
    canUseDatabase: vi.fn(() => true),
    listCustomStories: vi.fn(async () => [story]),
    updateQuizExclusions: vi.fn(async () => {}),
  };
});

beforeEach(() => {
  localStorage.setItem("teacherCustomStories", JSON.stringify([story]));
});

describe("TeacherQuizReviewPage", () => {
  it("lists quiz material, shows saved marks, and saves a new toggle", async () => {
    const { updateQuizExclusions } = await import("../services/database");
    render(<TeacherQuizReviewPage />);

    // Material rendered per word, saved mark visible as struck-through pool.
    expect(await screen.findByText("知道")).toBeInTheDocument();
    expect(screen.getByText(/曉得/)).toBeInTheDocument();
    expect(screen.getByText(/2 marked|已標記/)).toBeInTheDocument();

    // Toggle 知道's synonym off and save.
    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: "Exclude synonym for 知道" }));
    await userEvent.setup().click(screen.getByRole("button", { name: /Save marks|儲存標記/ }));

    expect(updateQuizExclusions).toHaveBeenCalledWith("s1", [
      { word: "一起", kind: "synonym", index: 0 },
      { word: "知道", kind: "synonym", index: 0 },
    ]);
  });
});
