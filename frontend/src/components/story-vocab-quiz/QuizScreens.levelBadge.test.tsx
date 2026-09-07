import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ModeSelectScreen } from "./QuizScreens";

const baseProps = {
  stars: 0 as const,
  weakEntries: [],
  startTier: vi.fn(),
  chooseWeakWords: vi.fn(),
  chooseInterimReview: vi.fn(),
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

  it("surfaces an interim 'review your misses' card before the diagnostic unlocks", () => {
    render(
      <ModeSelectScreen
        {...baseProps}
        interimReviewEntries={[
          { word: "附近", translation: "nearby", wordId: "word-1", pinyin: "fùjìn", bktValidationStatus: "APPROVED" },
          { word: "商店", translation: "shop", wordId: "word-2", pinyin: "shāngdiàn", bktValidationStatus: "APPROVED" },
        ]}
      />,
    );
    const card = screen.getByRole("button", { name: /Review your misses \(2\)/ });
    expect(card).toHaveTextContent("Your full weak-word list builds after all three rounds.");
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
