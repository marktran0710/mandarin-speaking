import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import SpeakingConversationFlow from "./SpeakingConversationFlow";
import type { ConversationTurn } from "./StoryRecorder/conversation";
import type { Topic } from "./StoryRecorder/storyContent";

/**
 * Regression for Dual Speaking Modes plan, Epic 6: SpeakingConversationFlow
 * used to pass masteryPassed/contentPassed to SpeakingFlowCard as bare
 * `true` (never the real analysis verdict) and modelAudioUrl as the
 * CHARACTER's own audioUrl (never the student's own optional model
 * response recording). Both are now wired to the real values.
 */

let lastProps: Record<string, unknown> = {};
vi.mock("../speaking-flow-card/SpeakingFlowCard", () => ({
  default: (props: Record<string, unknown>) => {
    lastProps = props;
    return <section aria-label="Record your story">Student recorder</section>;
  },
}));

const turns: ConversationTurn[] = [
  { id: "system-1", speaker: "system", text: "你週六下午有空嗎？", audioUrl: "/audio/character-line.wav" },
  {
    id: "student-1",
    speaker: "student",
    text: "有空，我們一起去喝下午茶。",
    targetText: "有空，我們一起去喝下午茶。",
    targetAudioUrl: "/audio/student-model-response.wav",
  },
];

const topic: Topic = {
  id: "conversation-topic",
  name: "Afternoon tea",
  images: ["/scene.png"],
  vocabulary: {},
  conversationTurns: turns,
};

describe("SpeakingConversationFlow result-flag and model-audio wiring", () => {
  it("passes the real (initially unpassed) mastery/content verdicts, never a hardcoded true", () => {
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

    expect(lastProps.masteryPassed).toBe(false);
    expect(lastProps.contentPassed).toBe(false);
  });

  it("passes the student's own targetAudioUrl as modelAudioUrl, never the character's audioUrl", () => {
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

    expect(lastProps.modelAudioUrl).toBe("/audio/student-model-response.wav");
    expect(lastProps.modelAudioUrl).not.toBe("/audio/character-line.wav");
  });

  it("leaves modelAudioUrl unset when the student turn has no model recording, rather than falling back to the character's audio", () => {
    const turnsWithoutModelAudio: ConversationTurn[] = [
      { id: "system-1", speaker: "system", text: "你好", audioUrl: "/audio/character-line.wav" },
      { id: "student-1", speaker: "student", text: "你好！" },
    ];
    render(
      <SpeakingConversationFlow
        topic={{ ...topic, conversationTurns: turnsWithoutModelAudio }}
        turns={turnsWithoutModelAudio}
        selectedImage="/scene.png"
        selectedImageIndex={0}
        onAddRecord={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "I’m ready to respond" }));

    expect(lastProps.modelAudioUrl).toBeUndefined();
  });
});
