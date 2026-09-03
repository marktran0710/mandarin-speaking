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
import * as database from "../../services/database";

vi.mock("../../services/database", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../services/database")>();
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

describe("StoryVocabQuiz pinyin/pos/synonym questions", () => {
  it("asks a pinyin question (no AI badge) when the random roll lands there, with the reading among the options", async () => {
    const user = userEvent.setup();
    const entries = [
      { word: "喝", translation: "to drink", pinyin: "hē" },
      { word: "看", translation: "to look", pinyin: "kàn" },
      { word: "做", translation: "to do", pinyin: "zuò" },
    ];
    // Only translation + pinyin are ever available for these entries (no
    // cloze/pos/synonym data), so a high roll lands on pinyin — the last
    // kind checked in pickQuestionKind.
    const randomSpy = vi.spyOn(Math, "random").mockReturnValue(FORCE_LAST_AVAILABLE_KIND);
    try {
      // The weak-words engine keeps the legacy question mix (no tier
      // policies), so these kind-forcing tests run through it.
      vi.mocked(database.getVocabQuizWeakWords).mockResolvedValue(entries.map((e) => e.word));
      render(
        <StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="s-legacy" studentId="stu" />,
      );
      await user.click(await screen.findByRole("button", { name: /Weak words/ }));

      const word = screen.getByRole("heading").textContent!;
      expect(screen.queryByLabelText("AI-generated question")).not.toBeInTheDocument();
      expect(
        screen.getByRole("group", { name: `How do you read ${word}?` }),
      ).toBeInTheDocument();

      const pinyinByWord: Record<string, string> = { 喝: "hē", 看: "kàn", 做: "zuò" };
      const options = optionButtons();
      expect(options.map((o) => o.textContent)).toContain(pinyinByWord[word]);

      await user.click(options.find((o) => o.textContent === pinyinByWord[word])!);
      expect(
        screen.getByRole("button", { name: `${pinyinByWord[word]} (correct answer)` }),
      ).toBeInTheDocument();
    } finally {
      randomSpy.mockRestore();
    }
  });

  it("asks a part-of-speech question (no AI badge) only for a word with teacher-authored pos data", async () => {
    const user = userEvent.setup();
    const entries = [
      { word: "貓", translation: "cat", pos: "N" },
      { word: "跑", translation: "to run", pos: "V" },
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

      const word = screen.getByRole("heading").textContent!;
      expect(screen.queryByLabelText("AI-generated question")).not.toBeInTheDocument();
      expect(
        screen.getByRole("group", { name: `What part of speech is ${word}?` }),
      ).toBeInTheDocument();

      const posByWord: Record<string, string> = { 貓: "N", 跑: "V" };
      const options = optionButtons();
      expect(options.map((o) => o.textContent)).toContain(posByWord[word]);

      await user.click(options.find((o) => o.textContent === posByWord[word])!);
      expect(
        screen.getByRole("button", { name: `${posByWord[word]} (correct answer)` }),
      ).toBeInTheDocument();
    } finally {
      randomSpy.mockRestore();
    }
  });

  it("never asks a pinyin question for a word with no computable reading (e.g. an English key word)", async () => {
    const user = userEvent.setup();
    const entries = [{ word: "market", translation: "marketplace" }];
    const randomSpy = vi.spyOn(Math, "random").mockReturnValue(FORCE_LAST_AVAILABLE_KIND);
    try {
      vi.mocked(database.getVocabQuizWeakWords).mockResolvedValue(entries.map((e) => e.word));
      render(
        <StoryVocabQuiz entries={entries} onDone={vi.fn()} storyId="s-legacy" studentId="stu" />,
      );
      await user.click(await screen.findByRole("button", { name: /Weak words/ }));

      // "market" has no pinyin reading, so even the highest roll must fall
      // back to a translation question instead of one with an empty answer.
      expect(
        screen.queryByRole("group", { name: "How do you read market?" }),
      ).not.toBeInTheDocument();
      expect(screen.getByRole("group", { name: "What does market mean?" })).toBeInTheDocument();
    } finally {
      randomSpy.mockRestore();
    }
  });

  it("never asks a part-of-speech question for a word with no authored pos data", async () => {
    const user = userEvent.setup();
    const entries = [{ word: "一", translation: "one" }];
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
        screen.queryByRole("group", { name: "What part of speech is 一?" }),
      ).not.toBeInTheDocument();
    } finally {
      randomSpy.mockRestore();
    }
  });

  it("asks a synonym question (with AI badge) whose correct answer is the synonym, not the original word", async () => {
    const user = userEvent.setup();
    const entries = [
      {
        word: "高興",
        translation: "happy",
        aiSynonym: [{ synonym: "開心", distractors: ["生氣", "累", "餓"] }],
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

      expect(screen.getByRole("heading")).toHaveTextContent("高興");
      expect(screen.getByLabelText("AI-generated question")).toBeInTheDocument();
      expect(
        screen.getByRole("group", { name: "Which word means the same as 高興?" }),
      ).toBeInTheDocument();

      const options = optionButtons();
      expect(options.map((o) => o.textContent)).toEqual(
        expect.arrayContaining(["開心", "生氣", "累", "餓"]),
      );
      // The original word itself must never appear as an option.
      expect(options.map((o) => o.textContent)).not.toContain("高興");

      await user.click(options.find((o) => o.textContent === "開心")!);
      expect(screen.getByRole("button", { name: "開心 (correct answer)" })).toBeInTheDocument();
    } finally {
      randomSpy.mockRestore();
    }
  });
});

