import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import JourneyStrip from "./JourneyStrip";

vi.mock("../services/database", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/database")>();
  return {
    ...actual,
    canUseDatabase: vi.fn(() => true),
    listVocabQuizAttempts: vi.fn(async () => [
      {
        id: "a1",
        storyId: "s-market",
        studentName: "Minh",
        studentId: "stu-1",
        mode: "tier2",
        completedAt: "2026-07-23T10:00:00Z",
        totalQuestions: 22,
        correctCount: 17, // gap 1 → near-miss
        totalTimeMs: 1000,
        questionResults: [],
      },
      {
        id: "a2",
        storyId: "s-market",
        studentName: "Minh",
        studentId: "stu-1",
        mode: "tier1",
        completedAt: "2026-07-22T10:00:00Z",
        totalQuestions: 20,
        correctCount: 15, // ⭐ earned → 1 star total
        totalTimeMs: 1000,
        questionResults: [],
      },
    ]),
  };
});

describe("JourneyStrip", () => {
  it("greets by name, shows total stars, and nudges the near-miss story with a jump button", async () => {
    const onJump = vi.fn();
    render(
      <JourneyStrip
        studentName="Minh"
        studentId="stu-1"
        storyCount={7}
        storyTitles={{ "s-market": "去市場買菜" }}
        onJumpToStory={onJump}
      />,
    );

    expect((await screen.findAllByText(/Minh/)).length).toBeGreaterThan(0);
    // 1 star earned of 7 stories × 3.
    expect(screen.getByText(/1 \/ 21/)).toBeInTheDocument();
    expect(screen.getByText(/去市場買菜/)).toBeInTheDocument();

    await userEvent.setup().click(screen.getByRole("button", { name: /去市場買菜/ }));
    expect(onJump).toHaveBeenCalledWith("s-market");
  });

  it("renders the welcome message without identity or attempts", () => {
    render(<JourneyStrip storyCount={3} storyTitles={{}} />);
    expect(screen.getByText(/開始/)).toBeInTheDocument();
  });
});
