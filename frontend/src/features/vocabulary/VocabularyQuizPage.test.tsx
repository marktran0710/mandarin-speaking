import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Topic } from "@entities/topic";
import type { TierMode } from "@entities/vocabulary";
import { useQuizSession } from "./hooks/useQuizSession";
import VocabularyQuizPage from "./VocabularyQuizPage";

vi.mock("./hooks/useQuizSession", () => ({ useQuizSession: vi.fn() }));
vi.mock("../../utils/studentSession", () => ({
  getStudentId: () => "student-1",
  getStudentScopeKey: () => "student-1",
  getStudentName: () => "Student One",
}));

function makeTopic(overrides: Partial<Topic> = {}): Topic {
  return {
    id: "story-1",
    name: "打電話",
    description: "desc",
    skillFocus: "conversation",
    images: [],
    vocabulary: {},
    ...overrides,
  };
}

function tierNumber(mode: TierMode | null): number {
  return mode === "tier1" ? 1 : mode === "tier2" ? 2 : mode === "tier3" ? 3 : 0;
}

/**
 * A minimal, controllable stand-in for the real useQuizSession — a genuine
 * hook (owns its own React state) rather than a static mock object, so
 * useVocabQuizFlow's tier-sequencing effects drive real re-renders exactly
 * like the production hook would. `stars` mirrors the real hook's rule:
 * only bumps when every question in the just-finished round was correct
 * (matching attemptEarnsStar's pass-threshold behavior at the boundary
 * this fake cares about — 100% right always passes, one wrong never does).
 */
function useFakeQuizSession() {
  const [screen, setScreen] = useState<"mode-select" | "quiz" | "summary">("mode-select");
  const [mode, setMode] = useState<TierMode | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [results, setResults] = useState<{ word: string; correct: boolean; correctAnswer: string }[]>([]);
  const [stars, setStars] = useState(0);

  const question = {
    kind: "translation" as const,
    word: mode ? `word-${mode}` : "word",
    options: ["right", "wrong"],
    correctTranslation: "right",
  };

  return {
    screen,
    mode,
    question,
    index: 0,
    questionLimit: 1,
    selected,
    results,
    stars,
    startTier: (tier: TierMode) => {
      setMode(tier);
      setScreen("quiz");
      setSelected(null);
      setResults([]);
    },
    choose: (option: string) => {
      setSelected(option);
      setResults([{ word: question.word, correct: option === "right", correctAnswer: "right" }]);
    },
    next: () => {
      const allCorrect = results.length > 0 && results.every((r) => r.correct);
      if (allCorrect) {
        const earned = tierNumber(mode);
        setStars((current) => (earned > current ? earned : current));
      }
      setScreen("summary");
    },
  };
}

describe("VocabularyQuizPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    vi.mocked(useQuizSession).mockImplementation(useFakeQuizSession as unknown as typeof useQuizSession);
  });

  it("runs tier1 -> tier2 -> tier3 in sequence and only finishes after tier 3's Finish click", () => {
    const onFinished = vi.fn();
    render(<VocabularyQuizPage topic={makeTopic()} lessonLabel="Lesson" onFinished={onFinished} />);
    fireEvent.click(screen.getByRole("button", { name: "Start Know It" }));

    // Tier 1: the learner starts the diagnostic round from the mode picker. The stimulus word encodes the
    // tier the fake hook was started with, so it doubles as proof of order.
    expect(screen.getByText("word-tier1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /right/ }));
    fireEvent.click(screen.getByRole("button", { name: /Next/ }));
    expect(screen.getByText("Passed")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(onFinished).not.toHaveBeenCalled();

    // Tier 2: only reached because tier1's round-result was passed + confirmed.
    expect(screen.getByText("word-tier2")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /right/ }));
    fireEvent.click(screen.getByRole("button", { name: /Next/ }));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(onFinished).not.toHaveBeenCalled();
    expect(JSON.parse(sessionStorage.getItem("studentPhaseFlags:student-1:story-1") ?? "{}").quiz).not.toBe(true);

    // Tier 3: only its Finish click (after a passed round-result) finishes the quiz.
    expect(screen.getByText("word-tier3")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /right/ }));
    fireEvent.click(screen.getByRole("button", { name: /Next/ }));
    fireEvent.click(screen.getByRole("button", { name: /Finish/ }));

    expect(onFinished).toHaveBeenCalledTimes(1);
    expect(JSON.parse(sessionStorage.getItem("studentPhaseFlags:student-1:story-1") ?? "{}").quiz).toBe(true);
  });

  it("shows Try Again (not Continue/Finish) and never advances or finishes when a tier is failed", () => {
    const onFinished = vi.fn();
    render(<VocabularyQuizPage topic={makeTopic()} lessonLabel="Lesson" onFinished={onFinished} />);
    fireEvent.click(screen.getByRole("button", { name: "Start Know It" }));

    expect(screen.getByText("word-tier1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /wrong/ }));
    fireEvent.click(screen.getByRole("button", { name: /Next/ }));

    expect(screen.getByText("Not quite")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Continue" })).not.toBeInTheDocument();
    expect(onFinished).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /Try again/i }));

    // Retrying re-starts the SAME tier fresh, never the next one.
    expect(screen.getByText("word-tier1")).toBeInTheDocument();
    expect(onFinished).not.toHaveBeenCalled();
  });
});
