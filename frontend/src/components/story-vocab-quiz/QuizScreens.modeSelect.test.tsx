import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ModeSelectScreen } from "./QuizScreens";

const dueWord = {
  wordId: "w1", word: "錢包", pLearned: 0.97, status: "STRONG" as const,
  observationCount: 5, correctCount: 5, incorrectCount: 0,
  reviewReason: "due" as const, dueOn: "2026-02-08",
};

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

  // A gentle nudge, not a forced flow: a card with real misses to review gets
  // a quiet pulsing cue (see 02-mode-results.css) so it catches the eye
  // without changing size, position, or blocking any other path.
  it("marks the interim 'review your misses' card as pending attention", () => {
    render(
      <ModeSelectScreen
        {...baseProps}
        interimReviewEntries={[
          { word: "附近", translation: "nearby", wordId: "word-1", pinyin: "fùjìn", bktValidationStatus: "APPROVED" },
        ]}
      />,
    );
    expect(screen.getByRole("button", { name: /Review your misses/ })).toHaveClass("is-pending-review");
  });

  it("marks the formal 'weak words' card as pending attention", () => {
    render(
      <ModeSelectScreen
        {...baseProps}
        weakEntries={[
          { word: "附近", translation: "nearby", wordId: "word-1", pinyin: "fùjìn", bktValidationStatus: "APPROVED" },
        ]}
      />,
    );
    expect(screen.getByRole("button", { name: /Weak words/ })).toHaveClass("is-pending-review");
  });

  it("does not mark the empty weak-words state as pending attention", () => {
    render(<ModeSelectScreen {...baseProps} />);
    const empty = screen.getByLabelText("Weak words");
    expect(empty).not.toHaveClass("is-pending-review");
  });

  const strongWord = {
    wordId: "word-1",
    word: "下午茶",
    meaning: "afternoon tea",
    pLearned: 0.98,
    status: "STRONG" as const,
    observationCount: 3,
    correctCount: 3,
    incorrectCount: 0,
  };

  it("shows a separate 'Due for review' card for SM-2 due words and starts that review", () => {
    const chooseDueReview = vi.fn();
    render(<ModeSelectScreen {...baseProps} dueWords={[dueWord]} chooseDueReview={chooseDueReview} />);
    const card = screen.getByRole("button", { name: /Due for review \(1\)/ });
    fireEvent.click(card);
    expect(chooseDueReview).toHaveBeenCalledTimes(1);
    // A strong-but-due word surfaces here, never in the weak-words card.
    expect(screen.queryByRole("button", { name: /Weak words/ })).not.toBeInTheDocument();
  });

  it("hides the due-review card when nothing is due", () => {
    render(<ModeSelectScreen {...baseProps} dueWords={[]} />);
    expect(screen.queryByRole("button", { name: /Due for review/ })).not.toBeInTheDocument();
  });

  it("confirms strong words only after all three rounds are passed (⭐⭐⭐)", () => {
    render(<ModeSelectScreen {...baseProps} stars={3} strongWords={[strongWord]} />);
    const strongWordsRegion = screen.getByRole("region", { name: "Strong words" });
    expect(strongWordsRegion).toHaveTextContent("Strong words (1)");
    expect(strongWordsRegion).toHaveTextContent("下午茶");
    expect(strongWordsRegion).toHaveTextContent("afternoon tea");
    expect(screen.getByRole("list", { name: "Strong vocabulary" })).toBeInTheDocument();
  });

  it("labels the same words as provisional ('on track') before ⭐⭐⭐", () => {
    // Rounds played but not all passed: the word is still only on track, but
    // the story isn't finished, so the UI must not over-claim mastery.
    render(<ModeSelectScreen {...baseProps} stars={2} strongWords={[strongWord]} />);
    const region = screen.getByRole("region", { name: "Words on track" });
    expect(region).toHaveTextContent("On track (1)");
    expect(region).toHaveTextContent("下午茶");
    expect(region).not.toHaveTextContent("Strong words");
    expect(screen.queryByRole("region", { name: "Strong words" })).not.toBeInTheDocument();
    // The word is still tappable to review — provisional only changes wording.
    expect(screen.getByRole("list", { name: "Strong vocabulary" })).toBeInTheDocument();
  });
});
