import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import JourneyBubble from "./JourneyBubble";

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

describe("JourneyBubble", () => {
  it("pulses as a quiz call-to-action while a story is below the star gate, and jumps into it on click", async () => {
    const onJump = vi.fn();
    render(
      <JourneyBubble
        studentName="Minh"
        studentId="stu-1"
        storyCount={7}
        storyTitles={{ "s-market": "去市場買菜" }}
        onJumpToStory={onJump}
      />,
    );

    // s-market has 1 of the 2 gate stars → needs-stars button showing ⭐ 1/2.
    const bubble = await screen.findByRole("button", { name: /去市場買菜/ });
    expect(bubble).toHaveClass("journey-bubble-locked");
    expect(await screen.findByText(/⭐ 1\/2/)).toBeInTheDocument();

    await userEvent.setup().click(bubble);
    expect(onJump).toHaveBeenCalledWith("s-market");
  });

  it("shows a display-only star dial once every story clears the gate", async () => {
    window.localStorage.setItem(
      "vocabQuizStars",
      JSON.stringify({ "s-market": 3 }),
    );
    try {
      render(
        <JourneyBubble
          storyCount={1}
          storyTitles={{ "s-market": "去市場買菜" }}
        />,
      );
      // No stories below the gate → status dial, not a button.
      expect(screen.queryByRole("button")).not.toBeInTheDocument();
      expect(screen.getByRole("status")).toHaveTextContent("⭐ 3/3");
    } finally {
      window.localStorage.removeItem("vocabQuizStars");
    }
  });

  it("shows the bare star tally on pages that don't know the story list", () => {
    render(<JourneyBubble studentName="Minh" />);
    expect(screen.getByRole("status")).toHaveTextContent("⭐ 0");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
