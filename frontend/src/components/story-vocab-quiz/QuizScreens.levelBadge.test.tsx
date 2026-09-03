import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ModeSelectScreen } from "./QuizScreens";

const baseProps = {
  stars: 0 as const,
  weakEntries: [],
  startTier: vi.fn(),
  chooseWeakWords: vi.fn(),
  showReview: vi.fn(),
};

describe("ModeSelectScreen — difficulty level badge", () => {
  it("defaults to Easy when no level prop is given", () => {
    render(<ModeSelectScreen {...baseProps} />);
    expect(screen.getByText("Easy")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Back to activities/ })).not.toBeInTheDocument();
  });

  it("shows Medium for a medium-level story", () => {
    render(<ModeSelectScreen {...baseProps} level="medium" />);
    expect(screen.getByText("Medium")).toBeInTheDocument();
    expect(screen.queryByText("Easy")).not.toBeInTheDocument();
  });

  it("shows Hard for a hard-level story", () => {
    render(<ModeSelectScreen {...baseProps} level="hard" />);
    expect(screen.getByText("Hard")).toBeInTheDocument();
  });

  it("keeps the story-wide weak-word summary visible when the current tier has no matching entries", () => {
    render(
      <ModeSelectScreen
        {...baseProps}
        priorityReviewWords={[{
          wordId: "word-1",
          word: "附近",
          pLearned: 0.2,
          status: "UNASSESSED",
          observationCount: 1,
          correctCount: 0,
          incorrectCount: 1,
        }]}
      />,
    );
    const weakWordsRegion = screen.getByRole("region", { name: "Weak words" });
    expect(weakWordsRegion).toHaveTextContent("Weak words (1)");
    expect(weakWordsRegion).toHaveTextContent("Open that level to practice them.");
    expect(weakWordsRegion).not.toHaveTextContent("附近");
    expect(weakWordsRegion).not.toHaveTextContent("1 observations");
  });

  it("shows the lesson's mastered words in a separate read-only summary", () => {
    render(
      <ModeSelectScreen
        {...baseProps}
        masteredWords={[{
          wordId: "word-1",
          word: "下午茶",
          meaning: "afternoon tea",
          pLearned: 0.98,
          status: "MASTERED",
          observationCount: 3,
          correctCount: 3,
          incorrectCount: 0,
        }]}
      />,
    );
    const masteredWordsRegion = screen.getByRole("region", { name: "Mastered words" });
    expect(masteredWordsRegion).toHaveTextContent("Mastered words (1)");
    expect(masteredWordsRegion).toHaveTextContent("下午茶");
    expect(masteredWordsRegion).toHaveTextContent("afternoon tea");
    expect(screen.getByRole("list", { name: "Mastered vocabulary" })).toBeInTheDocument();
  });
});
