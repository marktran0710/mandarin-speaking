import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import LearningOverview, { QuizGateStatus } from "./LearningOverview";
import type { LearningSummary, WorkspaceTopicSummary } from "../../types/studentWorkspace";

const summary: LearningSummary = {
  lessonProgress: 50,
  wordsToPractice: 5,
  todayGoal: { completed: 2, total: 3 },
  continueTarget: {
    storyId: "story-1",
    label: "週末去喝下午茶",
    progress: 40,
  },
};

const topicSummary: WorkspaceTopicSummary = {
  topic: {
    id: "story-1",
    name: "週末去喝下午茶",
    description: "Practice a weekend conversation.",
    skillFocus: "Story speaking",
    images: ["/scene-1.jpg"],
    vocabulary: { 0: ["下午茶", "週末"] },
  },
  quizGate: {
    status: "required",
    quizId: "story-1",
    reason: "Finish the vocabulary quiz before speaking practice.",
  },
  quizWordCount: 5,
  recordedSceneCount: 1,
};

describe("LearningOverview", () => {
  it("explains the quiz gate and sends the learner to the quiz CTA", async () => {
    const user = userEvent.setup();
    const onStartActivity = vi.fn();

    render(
      <LearningOverview
        summary={summary}
        topicSummary={topicSummary}
        onStartActivity={onStartActivity}
        onOpenProgress={vi.fn()}
        onOpenPractice={vi.fn()}
      />,
    );

    expect(screen.getAllByText("Quiz required first")).toHaveLength(2);
    expect(screen.getByRole("button", { name: /Take quiz to begin/ })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Take quiz to begin/ }));
    expect(onStartActivity).toHaveBeenCalledOnce();
  });

  it("renders the ready state after the quiz has been completed", () => {
    render(<QuizGateStatus gate={{ status: "completed", score: 3 }} />);
    expect(screen.getByText("Quiz complete")).toBeInTheDocument();
    expect(screen.getByText("Ready to start speaking practice")).toBeInTheDocument();
  });
});
