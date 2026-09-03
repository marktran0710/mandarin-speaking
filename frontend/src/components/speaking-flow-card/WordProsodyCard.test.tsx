import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import WordProsodyCard from "./WordProsodyCard";
import type { WordProsody } from "../story-recorder/StoryRecorder";

// The real drill records audio and calls the backend — stub it with a
// button that reports a pass, which is the only signal the card consumes.
vi.mock("./WordPracticeDrill", () => ({
  default: ({ onPass }: { onPass?: (token: string) => void }) => (
    <button type="button" onClick={() => onPass?.("在")}>
      fake-drill-pass
    </button>
  ),
}));

const failedItem = {
  token: "在",
  index: 0,
  passed: false,
  shape_accuracy: 40,
  tone_accuracy: 42,
  pitch_contour: [],
  feedback: "Tone fell short.",
} as unknown as WordProsody;

describe("WordProsodyCard", () => {
  it("turns from failed (red) to cleared (green) when its drill passes, and still reports the pass upward", async () => {
    const onDrillPass = vi.fn();
    const { container } = render(
      <WordProsodyCard item={failedItem} onDrillPass={onDrillPass} />,
    );

    const card = container.querySelector(".word-prosody-card")!;
    expect(card.className).toContain("word-prosody-failed");
    expect(card.className).not.toContain("word-prosody-cleared");

    await userEvent.setup().click(screen.getByText("fake-drill-pass"));

    expect(card.className).not.toContain("word-prosody-failed");
    expect(card.className).toContain("word-prosody-cleared");
    // The cleared badge appears so the color change reads as a verdict.
    expect(screen.getByText(/過關/)).toBeInTheDocument();
    expect(onDrillPass).toHaveBeenCalledWith("在");
  });
});
