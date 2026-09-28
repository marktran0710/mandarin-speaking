import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Topic } from "@entities/topic";
import { recordLocalStars } from "@entities/vocabulary";
import { canUseDatabase } from "../../services/database";
import { getVocabularyProgression, type VocabularyProgression } from "../../services/api/quiz-analytics";
import { getStudentScopeKey } from "../../utils/studentSession";
import StudentApp from "./StudentApp";

vi.mock("../../services/database", async (importOriginal) => ({
  ...await importOriginal<typeof import("../../services/database")>(),
  canUseDatabase: vi.fn(() => false),
}));
vi.mock("../../services/api/quiz-analytics", async (importOriginal) => ({
  ...await importOriginal<typeof import("../../services/api/quiz-analytics")>(),
  getVocabularyProgression: vi.fn(),
}));
vi.mock("../../utils/studentSession", () => ({
  getStudentId: () => "student-1",
  getStudentScopeKey: vi.fn(() => "student-1"),
  getStudentName: () => "Student One",
  isAdminSession: () => false,
}));
vi.mock("../../features/vocabulary/VocabularyQuizPage", () => ({
  default: () => <div data-testid="vocabulary-practice">Vocabulary Practice</div>,
}));

function topic(id = "preview-gate"): Topic {
  return {
    id, name: id, images: [], vocabulary: {},
    vocabAssessment: [{
      questionId: "q1", wordId: "w1", targetWord: "你好", pinyin: "ni3 hao3", pos: "phrase",
      simpleEnglishMeaning: "hello", level: "easy", difficultyWeight: 1,
      questionType: "basic_meaning_mcq", answerFormat: "single_choice", prompt: "Meaning?",
      options: ["hello", "goodbye"], correctAnswer: "hello", acceptedAnswers: ["hello"], explanation: "",
    }],
  };
}

function openLesson(id = "preview-gate") {
  fireEvent.click(within(screen.getByText(id, { selector: ".study-row-title" }).closest("article")!).getByRole("button"));
}

function phaseButton(label: string) {
  return within(screen.getByRole("navigation", { name: "課程階段" })).getByText(label).closest("button")!;
}

function serverProgress(quizStars: VocabularyProgression["quizStars"]): VocabularyProgression {
  const tier = { earned: false, correctCount: 0, totalQuestions: 0, score: 0, completedAt: null };
  return {
    storyId: "preview-gate", quizStars, requiredStars: 3,
    tiers: { tier1: tier, tier2: tier, tier3: tier }, speakingUnlocked: quizStars === 3,
    conversationAvailable: false, conversationUnlocked: quizStars === 3,
  };
}

describe("Vocabulary Preview prerequisite", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    vi.mocked(canUseDatabase).mockReturnValue(false);
    vi.mocked(getVocabularyProgression).mockReset();
    vi.mocked(getStudentScopeKey).mockReturnValue("student-1");
  });
  afterEach(() => { vi.restoreAllMocks(); });

  it.each([0, 3] as const)("requires the preview action before Vocabulary Practice even with %i saved stars", (stars) => {
    if (stars !== 0) recordLocalStars("preview-gate", stars);
    render(<StudentApp studentName="Student One" topics={[topic()]} onAddRecord={vi.fn()} onLogout={vi.fn()} />);
    openLesson();

    expect(phaseButton("詞彙練習")).toHaveAttribute("aria-disabled", "true");
    fireEvent.click(phaseButton("詞彙練習"));
    expect(screen.queryByTestId("vocabulary-practice")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "開始測驗" }));
    expect(phaseButton("詞彙練習")).not.toHaveAttribute("aria-disabled", "true");
    expect(screen.getByTestId("vocabulary-practice")).toBeInTheDocument();

    fireEvent.click(phaseButton("生詞預習"));
    expect(phaseButton("詞彙練習")).not.toHaveAttribute("aria-disabled", "true");
    fireEvent.click(phaseButton("詞彙練習"));
    expect(screen.getByTestId("vocabulary-practice")).toBeInTheDocument();
  });

  it.each([0, 3] as const)("does not let a server %i-star response complete Preview or open Vocabulary Practice", async (stars) => {
    vi.mocked(canUseDatabase).mockReturnValue(true);
    vi.mocked(getVocabularyProgression).mockResolvedValue(serverProgress(stars));
    render(<StudentApp studentName="Student One" topics={[topic()]} onAddRecord={vi.fn()} onLogout={vi.fn()} />);
    openLesson();
    await act(async () => {});

    expect(phaseButton("詞彙練習")).toHaveAttribute("aria-disabled", "true");
    expect(screen.queryByTestId("vocabulary-practice")).not.toBeInTheDocument();
    expect(phaseButton("生詞預習")).toHaveAttribute("aria-current", "page");
    expect(phaseButton("口語練習")).toHaveAttribute("aria-disabled", "true");
    expect(phaseButton("對話練習")).toHaveAttribute("aria-disabled", "true");
    fireEvent.click(screen.getByRole("button", { name: "開始測驗" }));
    expect(phaseButton("詞彙練習")).not.toHaveAttribute("aria-disabled", "true");
    expect(screen.getByTestId("vocabulary-practice")).toBeInTheDocument();
  });

  it("restores an actual completed Preview without requiring quiz stars", () => {
    sessionStorage.setItem("studentPhaseFlags:student-1:preview-gate", JSON.stringify({ vocab: true }));
    render(<StudentApp studentName="Student One" topics={[topic()]} onAddRecord={vi.fn()} onLogout={vi.fn()} />);
    openLesson();
    expect(phaseButton("詞彙練習")).not.toHaveAttribute("aria-disabled", "true");
    fireEvent.click(phaseButton("詞彙練習"));
    expect(screen.getByTestId("vocabulary-practice")).toBeInTheDocument();
  });

  it("does not treat the Quiz phase flag as completed Preview", () => {
    sessionStorage.setItem("studentPhaseFlags:student-1:preview-gate", JSON.stringify({ quiz: true }));
    render(<StudentApp studentName="Student One" topics={[topic()]} onAddRecord={vi.fn()} onLogout={vi.fn()} />);
    openLesson();
    expect(phaseButton("詞彙練習")).toHaveAttribute("aria-disabled", "true");
  });

  it("remembers Preview for the same lesson and keeps other lessons and students locked", () => {
    render(<StudentApp studentName="Student One" topics={[topic(), topic("other-lesson")]} onAddRecord={vi.fn()} onLogout={vi.fn()} />);
    openLesson();
    fireEvent.click(screen.getByRole("button", { name: "開始測驗" }));
    fireEvent.click(screen.getByRole("button", { name: "課程" }));
    openLesson("other-lesson");
    expect(phaseButton("詞彙練習")).toHaveAttribute("aria-disabled", "true");

    fireEvent.click(screen.getByRole("button", { name: "課程" }));
    openLesson();
    expect(phaseButton("詞彙練習")).not.toHaveAttribute("aria-disabled", "true");
    fireEvent.click(screen.getByRole("button", { name: "課程" }));
    vi.mocked(getStudentScopeKey).mockReturnValue("student-2");
    openLesson();
    expect(phaseButton("詞彙練習")).toHaveAttribute("aria-disabled", "true");
  });

  it("opens Vocabulary Practice after completing Preview when browser storage is unavailable", () => {
    render(<StudentApp studentName="Student One" topics={[topic()]} onAddRecord={vi.fn()} onLogout={vi.fn()} />);
    openLesson();
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("Unavailable"); });
    fireEvent.click(screen.getByRole("button", { name: "開始測驗" }));
    expect(phaseButton("詞彙練習")).not.toHaveAttribute("aria-disabled", "true");
    expect(screen.getByTestId("vocabulary-practice")).toBeInTheDocument();
  });
});
