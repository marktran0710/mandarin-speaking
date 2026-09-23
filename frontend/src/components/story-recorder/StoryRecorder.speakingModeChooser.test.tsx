import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import StoryRecorder from "./StoryRecorder";
import type { ConversationTurn } from "./StoryRecorder/conversation";
import type { Topic } from "./StoryRecorder/storyContent";

/** Dual Speaking Modes plan, Epic 4: Conversation Practice is a chosen
 * second Speaking mode, never a silent replacement for Story Practice. */

vi.mock("./StoryRecorderRuntime", () => ({
  default: () => <section aria-label="Legacy story practice">Legacy runtime</section>,
}));
vi.mock("./SpeakingConversationFlow", () => ({
  default: () => <section aria-label="Conversation practice">Conversation flow</section>,
}));

const turns: ConversationTurn[] = [
  { id: "system-1", speaker: "system", text: "你好", audioUrl: "/a.wav" },
  { id: "student-1", speaker: "student", text: "你好！", targetText: "你好！" },
  { id: "system-2", speaker: "system", text: "你好嗎？", audioUrl: "/b.wav" },
  { id: "student-2", speaker: "student", text: "我很好。", targetText: "我很好。" },
];

const conversationTopic: Topic = {
  id: "conversation-topic",
  name: "Conversation story",
  images: ["/scene.png"],
  vocabulary: {},
  conversationTurns: turns,
};

const legacyTopic: Topic = {
  id: "legacy-topic",
  name: "Legacy story",
  images: ["/scene.png"],
  vocabulary: {},
};

const baseProps = {
  selectedImage: "/scene.png",
  selectedImageIndex: 0,
  onImageSelect: vi.fn(),
  onImageChange: vi.fn(),
  onAddRecord: vi.fn(),
};

describe("StoryRecorder speaking mode chooser", () => {
  it("shows the chooser for a story with conversation content, instead of jumping straight into either mode", () => {
    render(<StoryRecorder {...baseProps} topic={conversationTopic} />);

    expect(screen.getByRole("region", { name: "Choose a speaking activity" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Legacy story practice" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Conversation practice" })).not.toBeInTheDocument();
  });

  it("mounts the legacy runtime after choosing Story Practice", () => {
    render(<StoryRecorder {...baseProps} topic={conversationTopic} />);
    fireEvent.click(screen.getAllByRole("button", { name: /Start/i })[0]);
    expect(screen.getByRole("region", { name: "Legacy story practice" })).toBeInTheDocument();
  });

  it("mounts the conversation flow after choosing Conversation Practice", () => {
    render(<StoryRecorder {...baseProps} topic={conversationTopic} />);
    fireEvent.click(screen.getAllByRole("button", { name: /Start/i })[1]);
    expect(screen.getByRole("region", { name: "Conversation practice" })).toBeInTheDocument();
  });

  it("never shows the chooser for a legacy story with no conversation content", () => {
    render(<StoryRecorder {...baseProps} topic={legacyTopic} />);
    expect(screen.queryByRole("region", { name: "Choose a speaking activity" })).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Legacy story practice" })).toBeInTheDocument();
  });
});
