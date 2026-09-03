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

describe("StoryVocabQuiz single-correct-answer guards", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  async function startTier2() {
    const { recordLocalStars } = await import("../../utils/quizTiers");
    recordLocalStars("s1", 1);
  }

  it("drops an AI translation distractor that differs from the correct answer only by case/punctuation", async () => {
    await startTier2();
    const user = userEvent.setup();
    render(
      <StoryVocabQuiz
        entries={[
          {
            word: "餐廳",
            translation: "restaurant",
            aiDistractors: ["Restaurant.", "hotel", "kitchen"],
          },
        ]}
        onDone={vi.fn()}
        storyId="s1"
      />,
    );
    await screen.findByRole("group", { name: "Quiz mode" });
    await user.click(screen.getByRole("button", { name: /Round 2/ }));

    const options = optionButtons().map((b) => b.textContent);
    expect(options).toContain("restaurant");
    expect(options).not.toContain("Restaurant.");
  });

  it("never offers a second word with the same translation as a reverse-question option", async () => {
    // Both words translate to "restaurant" — whichever is asked, the other
    // would be a second correct answer and must be filtered out.
    vi.spyOn(Math, "random").mockReturnValue(FORCE_LAST_AVAILABLE_KIND);
    const user = userEvent.setup();
    render(
      <StoryVocabQuiz
        entries={[
          { word: "餐廳", translation: "restaurant" },
          { word: "飯館", translation: "Restaurant." },
        ]}
        onDone={vi.fn()}
      />,
    );
    await screen.findByRole("group", { name: "Quiz mode" });
    await user.click(screen.getByRole("button", { name: /Round 1/ }));

    const options = optionButtons().map((b) => b.textContent);
    expect(options).toHaveLength(1);
    expect(["餐廳", "飯館"]).toContain(options[0]);
  });

  it("never offers a homophone of the spoken word as a listening option", async () => {
    await startTier2();
    vi.stubGlobal("speechSynthesis", { speak: vi.fn(), cancel: vi.fn() });
    vi.stubGlobal(
      "SpeechSynthesisUtterance",
      class {
        text: string;
        lang = "";
        constructor(text: string) {
          this.text = text;
        }
      },
    );
    try {
      // 他 and 她 are both read "tā" — by sound alone both would be correct.
      vi.spyOn(Math, "random").mockReturnValue(FORCE_LAST_AVAILABLE_KIND);
      const user = userEvent.setup();
      render(
        <StoryVocabQuiz
          entries={[
            { word: "他", translation: "he", pinyin: "tā" },
            { word: "她", translation: "she", pinyin: "tā" },
          ]}
          onDone={vi.fn()}
          storyId="s1"
        />,
      );
    await screen.findByRole("group", { name: "Quiz mode" });
      await user.click(screen.getByRole("button", { name: /Round 2/ }));

      const options = optionButtons().map((b) => b.textContent);
      expect(options).toHaveLength(1);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("never pads cloze options with a story word that shares the answer's translation", async () => {
    await startTier2();
    vi.spyOn(Math, "random").mockReturnValue(FORCE_LAST_AVAILABLE_KIND);
    const user = userEvent.setup();
    render(
      <StoryVocabQuiz
        entries={[
          {
            word: "高興",
            translation: "happy",
            aiCloze: [{ sentence: "我今天很高興。", distractors: ["生氣"] }],
          },
          {
            word: "開心",
            translation: "happy",
            aiCloze: [{ sentence: "他玩得很開心。", distractors: ["難過"] }],
          },
        ]}
        onDone={vi.fn()}
        storyId="s1"
      />,
    );
    await screen.findByRole("group", { name: "Quiz mode" });
    await user.click(screen.getByRole("button", { name: /Round 2/ }));

    // Whichever word the blank asks for, the other "happy" word would fit
    // the sentence just as well — it must never appear alongside it.
    const options = optionButtons().map((b) => b.textContent);
    expect(options.includes("高興") && options.includes("開心")).toBe(false);
  });

  it("styles pinyin options with the dedicated pinyin (mono) font class", async () => {
    await startTier2();
    vi.spyOn(Math, "random").mockReturnValue(FORCE_LAST_AVAILABLE_KIND);
    const user = userEvent.setup();
    render(
      <StoryVocabQuiz
        entries={[{ word: "喝茶", translation: "drink tea", pinyin: "hē chá" }]}
        onDone={vi.fn()}
        storyId="s1"
      />,
    );
    await screen.findByRole("group", { name: "Quiz mode" });
    await user.click(screen.getByRole("button", { name: /Round 2/ }));

    const group = screen.getByRole("group", { name: /How do you read/ });
    expect(group.className).toContain("vocab-quiz-options-pinyin");
  });
});

