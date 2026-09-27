import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import StudentSidebar from "./StudentSidebar";

describe("StudentSidebar", () => {
  it("provides pinyin tooltips for static navigation labels", () => {
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

    expect(screen.getByTitle("Kèchéng")).toBeInTheDocument();
    expect(screen.getByTitle("Jìndù")).toBeInTheDocument();
    expect(screen.getByTitle("Rùmén cèyàn")).toBeInTheDocument();
    expect(screen.getByTitle("Kǒuyǔ liànxí")).toBeInTheDocument();
  });

  it("keeps Conversation visible as a first-class lesson phase", () => {
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

    expect(screen.getByTitle("Kǒuyǔ liànxí")).toBeInTheDocument();
    expect(screen.getByTitle("Duìhuà liànxí")).toBeInTheDocument();
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

  it("locks phase-nav items beyond furthestPhase and never calls onNavigatePhase for them", () => {
    const onNavigatePhase = vi.fn();
    render(
      <StudentSidebar
        studentName="Student One"
        activeSection="study"
        activePhase="vocab-quiz"
        furthestPhase="vocab-quiz"
        speakingUnlocked
        onNavigateSection={vi.fn()}
        onNavigatePhase={onNavigatePhase}
        onLogout={vi.fn()}
      />,
    );

    const vocabQuiz = screen.getByTitle("Cíhuì liànxí").closest("button") as HTMLButtonElement;
    const speaking = screen.getByTitle("Kǒuyǔ liànxí").closest("button") as HTMLButtonElement;
    expect(vocabQuiz).not.toBeDisabled();
    expect(speaking).toBeDisabled();

    fireEvent.click(vocabQuiz);
    expect(onNavigatePhase).toHaveBeenCalledWith("vocab-quiz");

    onNavigatePhase.mockClear();
    fireEvent.click(speaking);
    expect(onNavigatePhase).not.toHaveBeenCalled();
  });

  it("locks Story Speaking specifically when speakingUnlocked is false, even if furthestPhase already reached it", () => {
    const onNavigatePhase = vi.fn();
    render(
      <StudentSidebar
        studentName="Student One"
        activeSection="study"
        activePhase="story-speaking"
        furthestPhase="story-speaking"
        speakingUnlocked={false}
        onNavigateSection={vi.fn()}
        onNavigatePhase={onNavigatePhase}
        onLogout={vi.fn()}
      />,
    );

    const speaking = screen.getByTitle("Kǒuyǔ liànxí").closest("button") as HTMLButtonElement;
    expect(speaking).toBeDisabled();
    fireEvent.click(speaking);
    expect(onNavigatePhase).not.toHaveBeenCalled();
  });
});
