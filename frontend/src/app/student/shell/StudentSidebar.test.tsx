import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import StudentSidebar from "./StudentSidebar";
import { computeLessonSteps } from "../lessonSteps";

const lockedAfterPreview = computeLessonSteps({
  hasQuiz: true,
  previewDone: true,
  quizDone: false,
  sceneCount: 2,
  scenesRecorded: 0,
  turnCount: 1,
  turnsRecorded: 0,
  conversationAvailable: true,
  submitted: false,
});

function phaseButton(phase: string) {
  return document.querySelector(`[data-phase="${phase}"]`) as HTMLButtonElement;
}

describe("StudentSidebar", () => {
  it("uses the transparent Lab logo for the sidebar brand mark", () => {
    render(
      <StudentSidebar
        studentName="Student One"
        activeSection="study"
        onNavigateSection={vi.fn()}
        onLogout={vi.fn()}
      />,
    );

    expect(document.querySelector(".sa-sidebar__brand-logo")).toHaveAttribute("src", "/logo.png");
  });

  it("shows every lesson step, with Story Speaking and Conversation grouped as a choice", () => {
    render(
      <StudentSidebar
        studentName="Student One"
        activeSection="study"
        activePhase="story-speaking"
        onNavigateSection={vi.fn()}
        onNavigatePhase={vi.fn()}
        onLogout={vi.fn()}
      />,
    );

    const group = screen.getByRole("group", { name: "選一個" });
    expect(within(group).getByRole("button", { name: /口語練習/ })).toBeInTheDocument();
    expect(within(group).getByRole("button", { name: /對話練習/ })).toBeInTheDocument();
    for (const phase of ["vocab-preview", "vocab-quiz", "story-speaking", "conversation", "submit"]) {
      expect(phaseButton(phase)).toBeInTheDocument();
    }
  });

  it("makes Placement a real, non-disabled nav button that calls onNavigateSection", () => {
    const onNavigateSection = vi.fn();
    render(
      <StudentSidebar
        studentName="Student One"
        activeSection="study"
        onNavigateSection={onNavigateSection}
        onLogout={vi.fn()}
      />,
    );

    const placementButton = screen.getByRole("button", { name: "入門測驗" });
    expect(placementButton).not.toBeDisabled();
    fireEvent.click(placementButton);
    expect(onNavigateSection).toHaveBeenCalledWith("placement");
  });

  it("renders quizStars/maxQuizStars and fills the track proportionally", () => {
    render(
      <StudentSidebar
        studentName="Student One"
        activeSection="study"
        quizStars={3}
        maxQuizStars={6}
        onNavigateSection={vi.fn()}
        onLogout={vi.fn()}
      />,
    );

    const starsSection = screen.getByLabelText("學習星星");
    expect(starsSection).toHaveTextContent("3");
    expect(starsSection).toHaveTextContent("/ 6");
    const fill = starsSection.querySelector(".sa-sidebar__stars-track span") as HTMLElement;
    expect(fill.style.width).toBe("50%");
  });

  it("hides the Stars card entirely when maxQuizStars is 0 (omitted), rather than showing a fake 0/0", () => {
    render(
      <StudentSidebar
        studentName="Student One"
        activeSection="study"
        onNavigateSection={vi.fn()}
        onLogout={vi.fn()}
      />,
    );

    expect(screen.queryByLabelText("學習星星")).not.toBeInTheDocument();
  });

  it("marks locked steps aria-disabled and explains why on click, without navigating", () => {
    const onNavigatePhase = vi.fn();
    render(
      <StudentSidebar
        studentName="Student One"
        activeSection="study"
        activePhase="vocab-quiz"
        steps={lockedAfterPreview}
        onNavigateSection={vi.fn()}
        onNavigatePhase={onNavigatePhase}
        onLogout={vi.fn()}
      />,
    );

    expect(phaseButton("vocab-quiz")).not.toHaveAttribute("aria-disabled");
    fireEvent.click(phaseButton("vocab-quiz"));
    expect(onNavigatePhase).toHaveBeenCalledWith("vocab-quiz");

    onNavigatePhase.mockClear();
    const speaking = phaseButton("story-speaking");
    expect(speaking).toHaveAttribute("aria-disabled", "true");
    fireEvent.click(speaking);
    expect(onNavigatePhase).not.toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent("做完三輪詞彙練習後解鎖");

    fireEvent.click(phaseButton("submit"));
    expect(screen.getByRole("status")).toHaveTextContent("先完成口語練習或對話練習");
  });

  it("shows a check on finished steps", () => {
    render(
      <StudentSidebar
        studentName="Student One"
        activeSection="study"
        activePhase="vocab-quiz"
        steps={lockedAfterPreview}
        onNavigateSection={vi.fn()}
        onNavigatePhase={vi.fn()}
        onLogout={vi.fn()}
      />,
    );

    expect(phaseButton("vocab-preview")).toHaveClass("is-done");
    expect(phaseButton("vocab-preview")).toHaveTextContent("已完成");
    expect(phaseButton("vocab-quiz")).not.toHaveClass("is-done");
  });
});
