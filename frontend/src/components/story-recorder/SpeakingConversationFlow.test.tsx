import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import SpeakingConversationFlow from "./SpeakingConversationFlow";
import type { ConversationTurn } from "./StoryRecorder/conversation";
import type { Topic } from "./StoryRecorder/storyContent";

vi.mock("../speaking-flow-card/SpeakingFlowCard", () => ({
  default: () => <section aria-label="Record your story">Student recorder</section>,
}));

const turns: ConversationTurn[] = [
  { id: "system-1", speaker: "system", text: "你週六下午有空嗎？", audioUrl: "/audio/system-1.wav" },
  { id: "student-1", speaker: "student", text: "有空，我們一起去喝下午茶。", pinyin: "Yǒu kòng, wǒmen yìqǐ qù hē xiàwǔchá." },
];

const topic: Topic = {
  id: "conversation-topic",
  name: "Afternoon tea",
  images: ["/scene.png"],
  vocabulary: {},
  conversationTurns: turns,
};

describe("SpeakingConversationFlow", () => {
  it("keeps the system turn audio-only, then exposes the student recorder", () => {
    render(
      <SpeakingConversationFlow
        topic={topic}
        turns={turns}
        selectedImage="/scene.png"
        selectedImageIndex={0}
        onAddRecord={vi.fn()}
      />,
    );

    expect(screen.getByRole("region", { name: "System turn" })).toBeInTheDocument();
    expect(screen.getByLabelText("System turn audio")).toHaveAttribute("src", "/audio/system-1.wav");
    expect(screen.queryByRole("region", { name: "Your turn" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "I’m ready to respond" }));

    expect(screen.getByRole("region", { name: "Your turn" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Record your story" })).toBeInTheDocument();
    expect(screen.getByText("有空，我們一起去喝下午茶。")).toBeInTheDocument();
  });
});
