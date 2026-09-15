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

describe("ModeSelectScreen", () => {
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

  const masteredWord = {
    wordId: "word-1",
    word: "下午茶",
    meaning: "afternoon tea",
    pLearned: 0.98,
    status: "MASTERED" as const,
    observationCount: 3,
    correctCount: 3,
    incorrectCount: 0,
  };

  it("confirms mastered words only after all three rounds are passed (⭐⭐⭐)", () => {
    render(<ModeSelectScreen {...baseProps} stars={3} masteredWords={[masteredWord]} />);
    const masteredWordsRegion = screen.getByRole("region", { name: "Mastered words" });
    expect(masteredWordsRegion).toHaveTextContent("Mastered words (1)");
    expect(masteredWordsRegion).toHaveTextContent("下午茶");
    expect(masteredWordsRegion).toHaveTextContent("afternoon tea");
    expect(screen.getByRole("list", { name: "Mastered vocabulary" })).toBeInTheDocument();
  });

  it("labels the same words as provisional ('on track') before ⭐⭐⭐, never 'mastered'", () => {
    // Rounds played but not all passed: BKT already flags the word MASTERED, but
    // the story isn't finished, so the UI must not over-claim mastery.
    render(<ModeSelectScreen {...baseProps} stars={2} masteredWords={[masteredWord]} />);
    const region = screen.getByRole("region", { name: "Words on track" });
    expect(region).toHaveTextContent("On track (1)");
    expect(region).toHaveTextContent("下午茶");
    expect(region).not.toHaveTextContent("Mastered words");
    expect(screen.queryByRole("region", { name: "Mastered words" })).not.toBeInTheDocument();
    // The word is still tappable to review — provisional only changes wording.
    expect(screen.getByRole("list", { name: "Mastered vocabulary" })).toBeInTheDocument();
  });
});
