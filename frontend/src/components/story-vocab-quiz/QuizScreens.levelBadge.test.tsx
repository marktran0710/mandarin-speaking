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
});
