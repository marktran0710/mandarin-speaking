import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SpeakingConversationFlow from "./SpeakingConversationFlow";
import type { ConversationTurn } from "./StoryRecorder/conversation";
import type { Topic } from "./StoryRecorder/storyContent";

const { listSpeakingProgress } = vi.hoisted(() => ({ listSpeakingProgress: vi.fn(async () => [] as any[]) }));

vi.mock("../../services/database", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../services/database")>();
  return {
    ...actual,
    canUseDatabase: () => true,
    listSpeakingProgress,
  };
});

vi.mock("../speaking-flow-card/SpeakingFlowCard", () => ({
  default: () => <section aria-label="Record your story">Student recorder</section>,
}));

// 3 exchanges = 6 raw turns.
const turns: ConversationTurn[] = [
  { id: "system-1", speaker: "system", text: "S1", audioUrl: "/a1.wav" },
  { id: "student-1", speaker: "student", text: "R1", targetText: "R1" },
  { id: "system-2", speaker: "system", text: "S2", audioUrl: "/a2.wav" },
  { id: "student-2", speaker: "student", text: "R2", targetText: "R2" },
  { id: "system-3", speaker: "system", text: "S3", audioUrl: "/a3.wav" },
  { id: "student-3", speaker: "student", text: "R3", targetText: "R3" },
];

const topic: Topic = {
  id: "resume-topic",
  name: "Resume test",
  images: ["/scene.png"],
  vocabulary: {},
  conversationTurns: turns,
};

describe("SpeakingConversationFlow resume-on-reopen (Epic 9)", () => {
  beforeEach(() => {
    listSpeakingProgress.mockReset();
    listSpeakingProgress.mockResolvedValue([]);
  });

  it("resumes at the next exchange after the furthest saved progress, not turn 0", async () => {
    listSpeakingProgress.mockResolvedValue([
      { studentId: "student-1", topicId: "resume-topic", sceneIndex: 0, attempts: 1, bestTone: 80, bestFluency: 80, masteryPassed: true, contentPassed: true, clearedWords: [], conversationId: "conversation:resume-topic", turnId: "student-1", turnIndex: 1 },
    ]);

    render(
      <SpeakingConversationFlow
        topic={topic}
        turns={turns}
        selectedImage="/scene.png"
        selectedImageIndex={0}
        onAddRecord={vi.fn()}
        studentId="student-1"
      />,
    );

    // Resumes at exchange 2 (turnIndex 2, the second system turn) - not
    // exchange 1.
    await screen.findByText("Exchange 2 of 3");
  });

  it("ignores another conversation's saved progress on the same topic", async () => {
    listSpeakingProgress.mockResolvedValue([
      { studentId: "student-1", topicId: "resume-topic", sceneIndex: 0, attempts: 1, bestTone: 80, bestFluency: 80, masteryPassed: true, contentPassed: true, clearedWords: [], conversationId: "conversation:some-other-topic", turnId: "student-1", turnIndex: 5 },
    ]);

    render(
      <SpeakingConversationFlow
        topic={topic}
        turns={turns}
        selectedImage="/scene.png"
        selectedImageIndex={0}
        onAddRecord={vi.fn()}
        studentId="student-1"
      />,
    );

    await screen.findByText("Exchange 1 of 3");
  });

  it("jumps straight to the summary when every exchange was already completed", async () => {
    listSpeakingProgress.mockResolvedValue([
      { studentId: "student-1", topicId: "resume-topic", sceneIndex: 0, attempts: 1, bestTone: 80, bestFluency: 80, masteryPassed: true, contentPassed: true, clearedWords: [], conversationId: "conversation:resume-topic", turnId: "student-3", turnIndex: 5 },
    ]);

    render(
      <SpeakingConversationFlow
        topic={topic}
        turns={turns}
        selectedImage="/scene.png"
        selectedImageIndex={0}
        onAddRecord={vi.fn()}
        studentId="student-1"
      />,
    );

    await screen.findByText("Nice work. You completed every response.");
  });

  it("starts at exchange 1 with no student id (no persistence to resume from)", () => {
    render(
      <SpeakingConversationFlow
        topic={topic}
        turns={turns}
        selectedImage="/scene.png"
        selectedImageIndex={0}
        onAddRecord={vi.fn()}
      />,
    );

    expect(screen.getByText("Exchange 1 of 3")).toBeInTheDocument();
    expect(listSpeakingProgress).not.toHaveBeenCalled();
  });
});
