import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import SpeakingConversationFlow from "./SpeakingConversationFlow";
import type { ConversationTurn } from "./StoryRecorder/conversation";
import type { Topic } from "./StoryRecorder/storyContent";

/**
 * Regression: on a student turn, ConversationTurnCard rendered the target
 * sentence/pinyin, and the real (unmocked) SpeakingFlowCard's
 * ModelRecordingPractice rendered the same sentence/pinyin again. This does
 * not mock SpeakingFlowCard (unlike SpeakingConversationFlow.test.tsx),
 * because the duplicate only exists in the real ModelRecordingPractice.
 */

afterEach(() => {
  vi.unstubAllGlobals();
});

const turns: ConversationTurn[] = [
  { id: "system-1", speaker: "system", text: "你週六下午有空嗎？", audioUrl: "/audio/system-1.wav" },
  {
    id: "student-1",
    speaker: "student",
    text: "有空，我們一起去喝下午茶。",
    pinyin: "Yǒu kòng, wǒmen yìqǐ qù hē xiàwǔchá.",
  },
];

const topic: Topic = {
  id: "conversation-topic",
  name: "Afternoon tea",
  images: ["/scene.png"],
  vocabulary: {},
  conversationTurns: turns,
};

describe("SpeakingConversationFlow — student turn prompt ownership", () => {
  it("shows the target sentence and pinyin exactly once, with the recorder and model audio still present", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("backend unreachable")));

    render(
      <SpeakingConversationFlow
        topic={topic}
        turns={turns}
        selectedImage="/scene.png"
        selectedImageIndex={0}
        onAddRecord={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "I’m ready to respond" }));

    expect(screen.getAllByText("有空，我們一起去喝下午茶。")).toHaveLength(1);
    expect(screen.getAllByText("Yǒu kòng, wǒmen yìqǐ qù hē xiàwǔchá.")).toHaveLength(1);
    expect(screen.getByRole("region", { name: "Record your story" })).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Listen and repeat model recording" }),
    ).toBeInTheDocument();
  });
});
