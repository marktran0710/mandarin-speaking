import { useState } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
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
  isAdminSession: () => false,
}));

function makeTopic(overrides: Partial<Topic> = {}): Topic {
  return {
    id: "story-1",
    name: "打電話",
    description: "desc",
    skillFocus: "conversation",
    images: [],
    vocabulary: {},
    vocabAssessment: [
      {
        questionId: "call-1-q1",
        wordId: "call-1",
        targetWord: "打電話",
        pinyin: "da3 dian4 hua4",
        pos: "V",
        simpleEnglishMeaning: "to make a phone call",
        level: "easy",
        difficultyWeight: 1,
        questionType: "basic_meaning_mcq",
        answerFormat: "single_choice",
        prompt: "What does 打電話 mean?",
        options: ["to make a phone call", "to eat"],
        correctAnswer: "to make a phone call",
        acceptedAnswers: ["to make a phone call"],
        explanation: "",
      },
    ],
    ...overrides,
  };
}

function tierNumber(mode: TierMode | null): number {
  return mode === "tier1" ? 1 : mode === "tier2" ? 2 : mode === "tier3" ? 3 : 0;
}

/**
 * A minimal, controllable stand-in for the real useQuizSession — a genuine
 * hook (owns its own React state) rather than a static mock object, so
 * useVocabQuizFlow's round-sequencing effects drive real re-renders exactly
 * like the production hook would. `stars` mirrors the real rule: finishing a
 * round earns it, whatever the score. A wrong first answer in a round offers
 * one hinted retry that never changes `correct`.
 */
function useFakeQuizSession() {
  const [screen, setScreen] = useState<"mode-select" | "quiz" | "summary">("mode-select");
  const [mode, setMode] = useState<TierMode | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [results, setResults] = useState<{ word: string; correct: boolean; correctAnswer: string; selectedAnswer: string; activityType: "diagnostic"; questionIndex: number; hintUsed?: boolean; retryCorrect?: boolean }[]>([]);
  const [stars, setStars] = useState(0);
  const [awaitingRetry, setAwaitingRetry] = useState(false);
  const [retryOutcome, setRetryOutcome] = useState<{ answer: string; correct: boolean } | null>(null);
  const [attempts, setAttempts] = useState<{ mode: TierMode; correctCount: number; totalQuestions: number; completedAt: string }[]>([]);

  const question = {
    kind: "translation" as const,
    word: mode ? `word-${mode}` : "word",
    options: ["right", "wrong", "other"],
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
    attempts,
    awaitingRetry,
    retryOutcome,
    sessionReady: true,
    startTier: (tier: TierMode) => {
      setMode(tier);
      setScreen("quiz");
      setSelected(null);
      setResults([]);
      setAwaitingRetry(false);
      setRetryOutcome(null);
    },
    choose: (option: string) => {
      setSelected(option);
      setResults([{ word: question.word, correct: option === "right", correctAnswer: "right", selectedAnswer: option, activityType: "diagnostic", questionIndex: 0 }]);
      setAwaitingRetry(option !== "right");
    },
    chooseRetry: (option: string) => {
      setResults((current) => current.map((result) => ({ ...result, hintUsed: true, retryCorrect: option === "right" })));
      setAwaitingRetry(false);
      setRetryOutcome({ answer: option, correct: option === "right" });
    },
    next: () => {
      const earned = tierNumber(mode);
      setStars((current) => (earned > current ? earned : current));
      setAttempts((current) => [...current, {
        mode: mode!,
        correctCount: results.filter((result) => result.correct).length,
        totalQuestions: results.length,
        completedAt: new Date(Date.now() + current.length).toISOString(),
      }]);
      setAwaitingRetry(false);
      setRetryOutcome(null);
      setScreen("summary");
    },
    returnToModes: () => setScreen("mode-select"),
  };
}

function answer(option: "right" | "wrong" | "other") {
  fireEvent.click(screen.getByRole("button", { name: new RegExp(option) }));
  fireEvent.click(screen.getByRole("button", { name: "提交答案" }));
}

describe("VocabularyQuizPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    sessionStorage.clear();
    vi.mocked(useQuizSession).mockImplementation(useFakeQuizSession as unknown as typeof useQuizSession);
  });

  it("runs the three rounds in order whatever the score, and finishes only from round 3's practice choice", () => {
    const onFinished = vi.fn();
    const onRoundCompleted = vi.fn();
    render(<VocabularyQuizPage topic={makeTopic()} lessonLabel="Lesson" onFinished={onFinished} onRoundCompleted={onRoundCompleted} />);

    // Rounds 2 and 3 are locked until the previous round is finished.
    const startButtons = () => screen.getAllByRole("button", { name: "開始" });
    expect(startButtons()[0]).not.toBeDisabled();
    expect(startButtons()[1]).toBeDisabled();
    fireEvent.click(startButtons()[0]);

    // Round 1, answered wrong twice: still finishes the round (score 0/100).
    expect(screen.getByText("word-tier1")).toBeInTheDocument();
    answer("wrong");
    answer("other");
    fireEvent.click(screen.getByRole("button", { name: "下一題" }));
    expect(screen.getByLabelText("0 / 100")).toBeInTheDocument();
    expect(onRoundCompleted).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "繼續" }));

    expect(screen.getByText("word-tier2")).toBeInTheDocument();
    answer("right");
    fireEvent.click(screen.getByRole("button", { name: "下一題" }));
    expect(screen.getByLabelText("100 / 100")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "繼續" }));
    expect(onFinished).not.toHaveBeenCalled();

    expect(screen.getByText("word-tier3")).toBeInTheDocument();
    answer("right");
    fireEvent.click(screen.getByRole("button", { name: "下一題" }));
    // A lesson without conversation turns exposes only its available path.
    expect(screen.getByRole("button", { name: "口語練習" })).not.toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "口語練習" }));

    expect(onFinished).toHaveBeenCalledTimes(1);
    expect(JSON.parse(localStorage.getItem("studentPhaseFlags:student-1:story-1") ?? "{}").quiz).toBe(true);
  });

  it("answers a wrong first try with a hint and one retry, never revealing the answer", () => {
    render(<VocabularyQuizPage topic={makeTopic()} lessonLabel="Lesson" onFinished={vi.fn()} />);
    fireEvent.click(screen.getAllByRole("button", { name: "開始" })[0]);

    answer("wrong");
    expect(screen.getByText("再試一次")).toBeInTheDocument();
    expect(screen.queryByText(/答案：/)).not.toBeInTheDocument();
    // The rejected option cannot be picked again.
    expect(screen.getByRole("button", { name: /wrong/ })).toBeDisabled();

    answer("right");
    expect(screen.getByText("這次對了！")).toBeInTheDocument();
    expect(screen.queryByText(/答案：/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "下一題" }));

    // The retry does not change the score, and the word goes on the review list.
    expect(screen.getByLabelText("0 / 100")).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "要再複習的詞語" })).getByText("word-tier1")).toBeInTheDocument();
  });

  it("lets the learner redo any round once all three are finished, showing each round's latest score", () => {
    render(<VocabularyQuizPage topic={makeTopic()} lessonLabel="Lesson" onFinished={vi.fn()} hasConversation />);
    fireEvent.click(screen.getAllByRole("button", { name: "開始" })[0]);
    answer("right");
    fireEvent.click(screen.getByRole("button", { name: "下一題" }));
    fireEvent.click(screen.getByRole("button", { name: "繼續" }));
    answer("wrong");
    answer("other");
    fireEvent.click(screen.getByRole("button", { name: "下一題" }));
    fireEvent.click(screen.getByRole("button", { name: "繼續" }));
    answer("right");
    fireEvent.click(screen.getByRole("button", { name: "下一題" }));
    // All three finished: the result offers the practice paths or the round list.
    expect(screen.getByRole("button", { name: "對話練習" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "回到三輪練習" }));

    const redoButtons = screen.getAllByRole("button", { name: "再做一次" });
    expect(redoButtons).toHaveLength(3);
    redoButtons.forEach((button) => expect(button).not.toBeDisabled());
    expect(screen.getByText("三輪都做完了，可以選任何一輪再練習。")).toBeInTheDocument();

    const roundCards = screen.getByRole("list", { name: "三輪練習" });
    expect(roundCards).toHaveTextContent("100/100");
    expect(roundCards).toHaveTextContent("0/100");

    fireEvent.click(redoButtons[1]);
    expect(screen.getByText("word-tier2")).toBeInTheDocument();
  });

  it("shows the shared empty state (never a blank screen) and finishes straight through when the lesson has no quiz", () => {
    const onFinished = vi.fn();
    render(<VocabularyQuizPage topic={makeTopic({ vocabAssessment: [] })} lessonLabel="Lesson" onFinished={onFinished} />);

    expect(screen.getByText("這一課沒有測驗。")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "繼續故事口說" }));
    expect(onFinished).toHaveBeenCalledTimes(1);
  });
});
