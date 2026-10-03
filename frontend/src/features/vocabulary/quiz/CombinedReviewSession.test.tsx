import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { studentUiCopy } from "../../../i18n/student-ui-copy";
import type { useCombinedReviewSession } from "../hooks/useCombinedReviewSession";
import CombinedReviewSession from "./CombinedReviewSession";

function reviewState() {
  const question = {
    slotId: "slot-1",
    position: 1,
    totalQuestions: 1,
    word: "你好",
    sourceStoryId: "lesson-1",
    questionType: "basic_meaning_mcq",
    dimension: "meaning" as const,
    reviewReason: "weak" as const,
    answerFormat: "single_choice" as const,
    prompt: "What does 你好 mean?",
    options: ["hello", "goodbye"],
  };
  return {
    session: {
      sessionId: "session-1",
      status: "active" as const,
      questionCount: 1,
      completedCount: 0,
      currentQuestion: question,
    },
    question,
    lastResult: null,
    weakCount: 1,
    dueCount: 0,
    availableCount: 1,
    queueReady: true,
    isStarting: false,
    isSubmitting: false,
    error: null,
    stale: false,
    start: vi.fn(),
    submit: vi.fn(() => new Promise<boolean>(() => undefined)),
    retrySave: vi.fn(),
    continueAfterFeedback: vi.fn(),
    defer: vi.fn(),
    discardStaleSession: vi.fn(),
    clearError: vi.fn(),
    refreshQueue: vi.fn(),
  };
}

describe("CombinedReviewSession", () => {
  it("waits for the saved server grade before showing feedback", () => {
    const initial = reviewState();
    const onClose = vi.fn();
    const onDiscardStale = vi.fn();
    const { rerender } = render(
      <CombinedReviewSession
        review={initial as unknown as ReturnType<typeof useCombinedReviewSession>}
        onClose={onClose}
        onDiscardStale={onDiscardStale}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "hello" }));
    fireEvent.click(screen.getByRole("button", { name: studentUiCopy.checkAnswer.zh }));

    expect(initial.submit).toHaveBeenCalledWith("hello", expect.any(Number));
    expect(screen.queryByText(studentUiCopy.correct.zh)).not.toBeInTheDocument();
    expect(screen.queryByText(studentUiCopy.notQuite.zh)).not.toBeInTheDocument();

    const saved = {
      ...initial,
      session: { ...initial.session, status: "completed" as const, completedCount: 1, currentQuestion: null },
      question: null,
      lastResult: {
        slotId: "slot-1",
        position: 1,
        word: "你好",
        reviewReason: "weak" as const,
        dimension: "meaning" as const,
        correct: false,
        correctAnswer: "hello",
        explanation: "你好 is a greeting.",
        selectedAnswer: "goodbye",
        answeredAt: "2026-10-03T00:00:00Z",
      },
    };
    rerender(
      <CombinedReviewSession
        review={saved as unknown as ReturnType<typeof useCombinedReviewSession>}
        onClose={onClose}
        onDiscardStale={onDiscardStale}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent(studentUiCopy.notQuite.zh);
    expect(screen.getByText("hello")).toBeInTheDocument();
    expect(screen.getByText("你好 is a greeting.")).toBeInTheDocument();
  });
});
