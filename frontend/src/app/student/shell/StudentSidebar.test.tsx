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

    expect(screen.getByRole("tooltip", { name: /^Kèchéng ·/ })).toBeInTheDocument();
    expect(screen.getByRole("tooltip", { name: /^Jìndù/ })).toBeInTheDocument();
    expect(screen.getByRole("tooltip", { name: /^Rùmén cèyàn/ })).toBeInTheDocument();
    expect(screen.getByRole("tooltip", { name: /^Kǒuyǔ liànxí/ })).toBeInTheDocument();
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

    expect(screen.getByText("口語練習")).toBeInTheDocument();
    expect(screen.getByText("對話練習")).toBeInTheDocument();
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
        vocabularyPracticeUnlocked
        onNavigateSection={vi.fn()}
        onNavigatePhase={onNavigatePhase}
        onLogout={vi.fn()}
      />,
    );

    const vocabQuiz = screen.getByText("詞彙練習").closest("button")!;
    const speaking = screen.getByText("口語練習").closest("button")!;
    expect(vocabQuiz).not.toBeDisabled();
    expect(speaking).toBeDisabled();

    fireEvent.click(vocabQuiz);
    expect(onNavigatePhase).toHaveBeenCalledWith("vocab-quiz");

    onNavigatePhase.mockClear();
    fireEvent.click(speaking);
    expect(onNavigatePhase).not.toHaveBeenCalled();
  });

  it("locks both practices when their shared gate is closed, even if furthestPhase already reached Story Speaking", () => {
    const onNavigatePhase = vi.fn();
    render(
      <StudentSidebar
        studentName="Student One"
        activeSection="study"
        activePhase="story-speaking"
        furthestPhase="story-speaking"
        practiceChoicesUnlocked={false}
        onNavigateSection={vi.fn()}
        onNavigatePhase={onNavigatePhase}
        onLogout={vi.fn()}
      />,
    );

    const speaking = screen.getByText("口語練習").closest("button")!;
    const conversation = screen.getByText("對話練習").closest("button")!;
    expect(speaking).toBeDisabled();
    expect(conversation).toBeDisabled();
    fireEvent.click(speaking);
    fireEvent.click(conversation);
    expect(onNavigatePhase).not.toHaveBeenCalled();
  });

  it.each(["vocab-preview", "story-speaking", "completion"] as const)(
    "requires completed Preview to open Vocabulary Practice at furthest phase %s",
    (furthestPhase) => {
      const onNavigatePhase = vi.fn();
      const props = {
        studentName: "Student One", activeSection: "study" as const, activePhase: "vocab-preview" as const,
        furthestPhase, practiceChoicesUnlocked: true,
        onNavigateSection: vi.fn(), onNavigatePhase, onLogout: vi.fn(),
      };
      const { rerender } = render(<StudentSidebar {...props} vocabularyPracticeUnlocked={false} />);
      const vocabularyPractice = screen.getByText("詞彙練習").closest("button")!;
      expect(vocabularyPractice).toBeDisabled();
      fireEvent.click(vocabularyPractice);
      expect(onNavigatePhase).not.toHaveBeenCalled();
      expect(screen.getByText("口語練習").closest("button")).not.toBeDisabled();
      expect(screen.getByText("對話練習").closest("button")).not.toBeDisabled();

      rerender(<StudentSidebar {...props} vocabularyPracticeUnlocked />);
      expect(vocabularyPractice).not.toBeDisabled();
      fireEvent.click(vocabularyPractice);
      expect(onNavigatePhase).toHaveBeenCalledWith("vocab-quiz");
    },
  );

  it.each(["vocab-preview", "vocab-quiz", "story-speaking", "conversation", "submit", "completion"] as const)(
    "uses the same practice gate for both modes at furthest phase %s",
    (furthestPhase) => {
      const onNavigatePhase = vi.fn();
      const { rerender } = render(
        <StudentSidebar studentName="Student One" activeSection="study" activePhase="vocab-preview"
          furthestPhase={furthestPhase} practiceChoicesUnlocked={false}
          onNavigateSection={vi.fn()} onNavigatePhase={onNavigatePhase} onLogout={vi.fn()} />,
      );
      const speaking = screen.getByText("口語練習").closest("button")!;
      const conversation = screen.getByText("對話練習").closest("button")!;
      expect(speaking).toBeDisabled();
      expect(conversation).toBeDisabled();
      fireEvent.click(speaking);
      fireEvent.click(conversation);
      expect(onNavigatePhase).not.toHaveBeenCalled();

      rerender(
        <StudentSidebar studentName="Student One" activeSection="study" activePhase="vocab-preview"
          furthestPhase={furthestPhase} practiceChoicesUnlocked
          onNavigateSection={vi.fn()} onNavigatePhase={onNavigatePhase} onLogout={vi.fn()} />,
      );
      expect(speaking).not.toBeDisabled();
      expect(conversation).not.toBeDisabled();
      fireEvent.click(speaking);
      fireEvent.click(conversation);
      expect(onNavigatePhase.mock.calls).toEqual([["story-speaking"], ["conversation"]]);
    },
  );
});
