import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StoryVocabQuiz, {
  buildQuizQuestions,
  collectQuizEntries,
  quizConceptId,
  quizItemId,
  type VocabQuizSummary,
} from "./StoryVocabQuiz";
import * as database from "../services/database";

vi.mock("../services/database", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/database")>();
  return {
    ...actual,
    canUseDatabase: vi.fn(() => true),
    getVocabQuizWeakWords: vi.fn(async () => []),
    listVocabQuizAttempts: vi.fn(async () => []),
  };
});

// The question-kind picker rolls Math.random() against a weighted list of
// whichever kinds are available for the entry (translation and pinyin are
// always available; cloze/pos/synonym only when the entry has that data —
// see pickQuestionKind in StoryVocabQuiz.tsx). Mocking Math.random() to 0
// always lands on the first-checked kind, translation (weight > 0, checked
// first) — every test in this file defaults to that below, since most were
// written before pinyin/cloze/pos/synonym existed and assume translation
// questions throughout; individual tests override the mock to exercise a
// specific other kind. Mocking it close to 1 always lands on the
// last-available kind — convenient when an entry gives exactly one "extra"
// kind of data, making that the last (and therefore selected) kind.
const FORCE_TRANSLATION = 0;
const FORCE_LAST_AVAILABLE_KIND = 0.999;

beforeEach(() => {
  vi.spyOn(Math, "random").mockReturnValue(FORCE_TRANSLATION);
});

afterEach(() => {
  vi.restoreAllMocks();
});

function optionButtons() {
  return screen
    .getAllByRole("button")
    .filter((b) => b.className.includes("vocab-quiz-option"));
}

/** Answers the currently-shown question, picking a definitely-correct or
 * definitely-wrong option by comparing each rendered option's text against
 * the word's known correct translation — needed since Strikes/Speed have no
 * manual "Finish" button, so tests drive them to a deterministic end (3
 * wrong in a row, or a fixed question count) instead. */
async function answerCurrentQuestion(
  user: ReturnType<typeof userEvent.setup>,
  correct: boolean,
  translationByWord: Record<string, string>,
) {
  const word = screen.getByRole("heading").textContent!;
  const correctTranslation = translationByWord[word];
  const buttons = optionButtons();
  const target = correct
    ? buttons.find((b) => b.textContent === correctTranslation)
    : buttons.find((b) => b.textContent !== correctTranslation);
  await user.click(target!);
}

describe("StoryVocabQuiz AI badge + cloze questions", () => {
  it("shows the AI badge on a translation question whose options draw from AI-generated distractors", async () => {
    const user = userEvent.setup();
    const entries = [
      { word: "喝", translation: "to drink", aiDistractors: ["to buy", "to look", "to do"] },
    ];
    const randomSpy = vi.spyOn(Math, "random").mockReturnValue(FORCE_TRANSLATION);
    try {
      // The weak-words engine keeps the legacy question mix (no tier
      // policies), so these kind-forcing tests run through it.
      vi.mocked(database.getVocabQuizWeakWords).mockResolvedValue(entries.map((e) => e.word));
      render(
        <StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="s-legacy" studentId="stu" />,
      );
      await user.click(await screen.findByRole("button", { name: /Weak words/ }));

      expect(screen.getByRole("heading")).toHaveTextContent("喝");
      expect(screen.getByLabelText("AI-generated question")).toBeInTheDocument();
    } finally {
      randomSpy.mockRestore();
    }
  });

  it("shows no AI badge on a translation question that has no AI-generated distractors", async () => {
    const user = userEvent.setup();
    const entries = [
      { word: "一", translation: "one" },
      { word: "二", translation: "two" },
    ];
    const randomSpy = vi.spyOn(Math, "random").mockReturnValue(FORCE_TRANSLATION);
    try {
      // The weak-words engine keeps the legacy question mix (no tier
      // policies), so these kind-forcing tests run through it.
      vi.mocked(database.getVocabQuizWeakWords).mockResolvedValue(entries.map((e) => e.word));
      render(
        <StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="s-legacy" studentId="stu" />,
      );
      await user.click(await screen.findByRole("button", { name: /Weak words/ }));

      expect(screen.queryByLabelText("AI-generated question")).not.toBeInTheDocument();
    } finally {
      randomSpy.mockRestore();
    }
  });

  it("mixes in a cloze question (sentence with a blank, Chinese-word options) when the word has cached AI cloze candidates", async () => {
    const user = userEvent.setup();
    const entries = [
      {
        word: "喝",
        translation: "to drink",
        aiCloze: [{ sentence: "我要喝水。", distractors: ["買", "看", "做"] }],
      },
    ];
    const randomSpy = vi.spyOn(Math, "random").mockReturnValue(FORCE_LAST_AVAILABLE_KIND);
    try {
      // The weak-words engine keeps the legacy question mix (no tier
      // policies), so these kind-forcing tests run through it.
      vi.mocked(database.getVocabQuizWeakWords).mockResolvedValue(entries.map((e) => e.word));
      render(
        <StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="s-legacy" studentId="stu" />,
      );
      await user.click(await screen.findByRole("button", { name: /Weak words/ }));

      expect(
        screen.getByRole("group", { name: "Which word fits the blank?" }),
      ).toBeInTheDocument();
      expect(screen.getByRole("heading")).toHaveTextContent("我要____水。");
      expect(screen.getByLabelText("AI-generated question")).toBeInTheDocument();

      const options = optionButtons();
      expect(options.map((o) => o.textContent)).toEqual(
        expect.arrayContaining(["喝", "買", "看", "做"]),
      );

      await user.click(options.find((o) => o.textContent === "喝")!);
      expect(screen.getByRole("button", { name: "喝 (correct answer)" })).toBeInTheDocument();
    } finally {
      randomSpy.mockRestore();
    }
  });

  it("never asks a cloze question for a word with no cached AI cloze candidates, even when the random roll would allow it", async () => {
    const user = userEvent.setup();
    const entries = [{ word: "一", translation: "one", pinyin: "yī" }];
    const randomSpy = vi.spyOn(Math, "random").mockReturnValue(FORCE_LAST_AVAILABLE_KIND);
    try {
      // The weak-words engine keeps the legacy question mix (no tier
      // policies), so these kind-forcing tests run through it.
      vi.mocked(database.getVocabQuizWeakWords).mockResolvedValue(entries.map((e) => e.word));
      render(
        <StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="s-legacy" studentId="stu" />,
      );
      await user.click(await screen.findByRole("button", { name: /Weak words/ }));

      // With no cloze/pos/synonym data, pinyin is the only other kind ever
      // available, so a high random roll lands there instead of cloze.
      expect(
        screen.queryByRole("group", { name: "Which word fits the blank?" }),
      ).not.toBeInTheDocument();
      expect(screen.getByRole("group", { name: "How do you read 一?" })).toBeInTheDocument();
    } finally {
      randomSpy.mockRestore();
    }
  });
});

