import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ConversationScriptFeedback, { deriveResponseTokenStates } from "./ConversationScriptFeedback";
import type { PraatMetrics, WordProsody } from "./StoryRecorder/types";

function token(overrides: Partial<WordProsody> & { token: string; passed: boolean | null }): WordProsody {
  return {
    index: 0,
    start_time: 0,
    end_time: 0,
    pitch_contour: [],
    ...overrides,
  } as WordProsody;
}

describe("deriveResponseTokenStates", () => {
  it("marks every character unmeasured when there is no analysis yet", () => {
    expect(deriveResponseTokenStates("你好", null)).toEqual([
      { char: "你", state: "unmeasured" },
      { char: "好", state: "unmeasured" },
    ]);
  });

  it("marks a matched, passing character as passed", () => {
    const metrics = {
      transcription: "你",
      word_prosody: [token({ token: "你", passed: true })],
    } as PraatMetrics;
    const [first] = deriveResponseTokenStates("你", metrics);
    expect(first.state).toBe("passed");
  });

  it("marks a matched but failing character as pronunciation_attention", () => {
    const metrics = {
      transcription: "你",
      word_prosody: [token({ token: "你", passed: false })],
    } as PraatMetrics;
    const [first] = deriveResponseTokenStates("你", metrics);
    expect(first.state).toBe("pronunciation_attention");
  });

  it("marks a character never said at all as mismatch", () => {
    const metrics = { transcription: "", word_prosody: [] as WordProsody[] } as PraatMetrics;
    const [first] = deriveResponseTokenStates("你", metrics);
    expect(first.state).toBe("mismatch");
  });
});

describe("ConversationScriptFeedback", () => {
  it("shows the script neutrally, with no color classes, before it is revealed", () => {
    const metrics = {
      transcription: "你",
      word_prosody: [token({ token: "你", passed: false })],
    } as PraatMetrics;
    const { container } = render(
      <ConversationScriptFeedback targetScript="你好" praatMetrics={metrics} revealed={false} />,
    );
    expect(screen.getByText("你好")).toBeInTheDocument();
    expect(container.querySelector(".conversation-script-feedback__token")).not.toBeInTheDocument();
  });

  it("shows per-character colored tokens once revealed", () => {
    const metrics = {
      transcription: "你",
      word_prosody: [token({ token: "你", passed: true })],
    } as PraatMetrics;
    const { container } = render(
      <ConversationScriptFeedback targetScript="你好" praatMetrics={metrics} revealed />,
    );
    const tokens = container.querySelectorAll(".conversation-script-feedback__token");
    expect(tokens).toHaveLength(2);
    expect(tokens[0]).toHaveClass("conversation-script-feedback__token--passed");
    expect(tokens[1]).toHaveClass("conversation-script-feedback__token--mismatch");
  });
});
