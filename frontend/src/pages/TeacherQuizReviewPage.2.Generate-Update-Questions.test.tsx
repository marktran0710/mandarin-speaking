import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TeacherQuizReviewPage from "./TeacherQuizReviewPage";
import { buildMaterialSnapshot } from "../utils/quizMaterialDiff";
import { storyToTopic, type CustomTeacherStory } from "../utils/teacherStories";

const story = {
  id: "s1",
  title: "測試故事",
  learningGoal: "goal",
  published: true,
  lessonNumber: 5,
  frames: [
    {
      imageUrl: "u",
      prompt: "p",
      vocabulary: "知道,一起",
      vocabularyPinyin: "zhīdào,yìqǐ",
      vocabularyTranslation: "to know,together",
      vocabularySynonym: JSON.stringify([
        [{ synonym: "曉得", distractors: ["不懂"] }],
        [{ synonym: "共同", distractors: ["分開"] }],
      ]),
    },
  ],
  quizExclusions: [{ word: "一起", kind: "synonym", index: 0 }],
};

const storyLesson7: CustomTeacherStory = {
  id: "s2",
  title: "第二個故事",
  learningGoal: "goal",
  published: true,
  lessonNumber: 7,
  frames: [
    {
      imageUrl: "u2",
      prompt: "p2",
      vocabulary: "茶",
      vocabularyPinyin: "chá",
      vocabularyTranslation: "tea",
    },
  ],
};

let mockStories: CustomTeacherStory[] = [story];

vi.mock("../services/database", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/database")>();
  return {
    ...actual,
    canUseDatabase: vi.fn(() => true),
    listCustomStories: vi.fn(async () => mockStories),
    updateQuizExclusions: vi.fn(async () => {}),
    validateQuizMaterial: vi.fn(async () => []),
    approveQuizMaterial: vi.fn(async () => {}),
    saveQuizPendingApprovals: vi.fn(async () => {}),
    replaceQuizQuestion: vi.fn(async () => {}),
    generateVocabDistractors: vi.fn(async () => []),
    generateVocabCloze: vi.fn(async () => []),
    generateVocabSynonym: vi.fn(async () => []),
    updateVocabularyDistractors: vi.fn(async () => {}),
    updateVocabularyCloze: vi.fn(async () => {}),
    updateVocabularySynonym: vi.fn(async () => {}),
  };
});

function setStories(stories: CustomTeacherStory[]) {
  mockStories = stories;
  localStorage.setItem("teacherCustomStories", JSON.stringify(stories));
}

beforeEach(() => {
  vi.clearAllMocks();
  setStories([story]);
});

describe("Generate / Update Questions", () => {
  const storyWithNoMaterial: CustomTeacherStory = {
    id: "s3",
    title: "全新故事",
    learningGoal: "goal",
    published: true,
    lessonNumber: 9,
    frames: [
      {
        imageUrl: "u3",
        prompt: "p3",
        vocabulary: "知道",
        vocabularyTranslation: "to know",
      },
    ],
  };

  const storyWithFullSynonymMaterial: CustomTeacherStory = {
    id: "s4",
    title: "Changed review",
    learningGoal: "goal",
    published: true,
    lessonNumber: 10,
    frames: [
      {
        imageUrl: "u4",
        prompt: "p4",
        vocabulary: "alpha",
        vocabularyTranslation: "first letter",
        vocabularyDistractors: JSON.stringify([["d1", "d2", "d3", "d4", "d5", "d6", "d7", "d8"]]),
        vocabularyCloze: JSON.stringify([
          [
            { sentence: "alpha cloze one", distractors: ["c1"] },
            { sentence: "alpha cloze two", distractors: ["c2"] },
            { sentence: "alpha cloze three", distractors: ["c3"] },
            { sentence: "alpha cloze four", distractors: ["c4"] },
          ],
        ]),
        vocabularySynonym: JSON.stringify([
          [
            { synonym: "old match", distractors: ["old miss"] },
            { synonym: "kept two", distractors: ["miss two"] },
            { synonym: "kept three", distractors: ["miss three"] },
            { synonym: "kept four", distractors: ["miss four"] },
          ],
        ]),
      },
    ],
  };

  const storyWithDroppedSnapshot: CustomTeacherStory = {
    id: "s5",
    title: "Removed review",
    learningGoal: "goal",
    published: true,
    lessonNumber: 11,
    quizMaterialSnapshot: {
      easy: [
        {
          word: "dropped",
          translation: "gone",
          distractors: [],
          cloze: [{ sentence: "dropped was here", distractors: ["other choice"] }],
          synonym: [],
        },
      ],
    },
    frames: [
      {
        imageUrl: "u5",
        prompt: "p5",
        vocabulary: "alpha",
        vocabularyTranslation: "first letter",
      },
    ],
  };

  it("shows only the action relevant to the current review phase", async () => {
    const { validateQuizMaterial } = await import("../services/database");
    setStories([storyWithNoMaterial]);
    render(<TeacherQuizReviewPage />);
    expect(await screen.findByRole("button", { name: /Generate Questions/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Validate Questions/ })).not.toBeInTheDocument();

    setStories([story]);
    render(<TeacherQuizReviewPage />);
    const validateButton = await screen.findByRole("button", { name: /Validate Questions/ });
    expect(screen.queryByRole("button", { name: /Update Questions/ })).not.toBeInTheDocument();

    (validateQuizMaterial as ReturnType<typeof vi.fn>).mockResolvedValue([
      { word: "知道", kind: "synonym", poolIndex: 0, status: "suspicious", reason: "duplicate answer" },
    ]);
    await userEvent.setup().click(validateButton);
    expect(await screen.findByRole("button", { name: /Update Questions/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Validate Questions/ })).not.toBeInTheDocument();
  });

  it("generates, reveals a new candidate, and only persists it once accepted and applied", async () => {
    const {
      generateVocabDistractors,
      generateVocabCloze,
      generateVocabSynonym,
      updateVocabularyDistractors,
    } = await import("../services/database");
    (generateVocabDistractors as ReturnType<typeof vi.fn>).mockResolvedValue([
      { word: "知道", distractors: ["to see", "to hear", "to say"] },
    ]);
    (generateVocabCloze as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    (generateVocabSynonym as ReturnType<typeof vi.fn>).mockResolvedValue([]);

    setStories([storyWithNoMaterial]);
    render(<TeacherQuizReviewPage />);
    const user = userEvent.setup();
    await screen.findByText("知道");

    await user.click(screen.getByRole("button", { name: /Generate Questions/ }));

    // Reveals as a 🆕 New candidate; Apply is hidden until it is decided.
    const distractorLine = await screen.findByText(/New distractors/);
    expect(distractorLine.closest(".diff-row")).toHaveClass("row-add");
    expect(screen.getByText(/🆕 New/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Apply Changes/ })).not.toBeInTheDocument();
    expect(updateVocabularyDistractors).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /Accept$/ }));
    expect(await screen.findByText(/Added/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Apply Changes/ }));

    expect(updateVocabularyDistractors).toHaveBeenCalledWith("s3", [
      { frameIndex: 0, wordIndex: 0, distractors: ["to see", "to hear", "to say"] },
    ]);
  });

  it("safety-filters duplicate and answer-leaking values when Generate Questions is clicked", async () => {
    const {
      generateVocabDistractors,
      generateVocabCloze,
      generateVocabSynonym,
      updateVocabularyDistractors,
    } = await import("../services/database");
    (generateVocabDistractors as ReturnType<typeof vi.fn>).mockResolvedValue([
      { word: "知道", distractors: ["to know", "to see", "To see"] },
    ]);
    (generateVocabCloze as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    (generateVocabSynonym as ReturnType<typeof vi.fn>).mockResolvedValue([]);

    setStories([storyWithNoMaterial]);
    render(<TeacherQuizReviewPage />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Generate Questions/ }));

    expect(await screen.findByText(/2 duplicate or answer-leaking generated values were removed/)).toBeInTheDocument();
    await screen.findByText(/New distractors/);
    await user.click(screen.getByRole("button", { name: /Accept$/ }));
    await user.click(screen.getByRole("button", { name: /Apply Changes/ }));

    expect(updateVocabularyDistractors).toHaveBeenCalledWith("s3", [
      { frameIndex: 0, wordIndex: 0, distractors: ["to see"] },
    ]);
  });

  it("shows an error when question generation fails", async () => {
    const { generateVocabCloze } = await import("../services/database");
    (generateVocabCloze as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error("rate limited"));

    setStories([storyWithNoMaterial]);
    render(<TeacherQuizReviewPage />);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: /Generate Questions/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Generate failed. Try again in a moment");
  });

  it("renders a changed candidate diff and replaces the old question with the new value", async () => {
    const { generateVocabSynonym, replaceQuizQuestion, validateQuizMaterial } = await import("../services/database");
    (validateQuizMaterial as ReturnType<typeof vi.fn>).mockResolvedValue([
      { word: "alpha", kind: "synonym", poolIndex: 0, status: "suspicious", reason: "too obvious" },
    ]);
    (generateVocabSynonym as ReturnType<typeof vi.fn>).mockResolvedValue([
      { word: "alpha", synonym: "new match", distractors: ["new miss"] },
    ]);

    setStories([storyWithFullSynonymMaterial]);
    render(<TeacherQuizReviewPage />);
    const user = userEvent.setup();
    await screen.findByText("Changed review");
    await user.click(screen.getByRole("button", { name: /Validate Questions/ }));
    await screen.findByText(/too obvious/);
    await user.click(screen.getByRole("button", { name: /Update Questions/ }));

    const oldLine = (await screen.findAllByText(/old match/))
      .map((node) => node.closest(".diff-row"))
      .find((node): node is HTMLElement => node instanceof HTMLElement && node.classList.contains("row-del"));
    expect(oldLine).toHaveClass("row-del");
    const newLine = await screen.findByText(/new match/);
    expect(newLine.closest(".diff-row")).toHaveClass("row-add");

    const row = newLine.closest(".tqr-pending-change");
    expect(row).not.toBeNull();
    await user.click(within(row as HTMLElement).getByRole("button", { name: /Accept$/ }));
    await user.click(screen.getByRole("button", { name: /Apply Changes/ }));

    await waitFor(() =>
      expect(replaceQuizQuestion).toHaveBeenCalledWith(
        "s4",
        0,
        0,
        "synonym",
        0,
        { synonym: "new match", distractors: ["new miss"] },
      ),
    );
  });

  it("renders a removed candidate diff and soft-deletes it through quiz exclusions", async () => {
    const { generateVocabSynonym, updateQuizExclusions } = await import("../services/database");
    (generateVocabSynonym as ReturnType<typeof vi.fn>).mockResolvedValue([]);

    setStories([storyWithDroppedSnapshot]);
    render(<TeacherQuizReviewPage />);
    const user = userEvent.setup();
    await screen.findByText("Removed review");
    await user.click(screen.getByRole("button", { name: /Generate Questions/ }));

    const removedLine = await screen.findByText(/other choice/);
    expect(removedLine.closest(".diff-row")).toHaveClass("row-del");
    expect(screen.getByText(/dropped since the last review/)).toBeInTheDocument();

    const row = removedLine.closest(".tqr-pending-change");
    expect(row).not.toBeNull();
    await user.click(within(row as HTMLElement).getByRole("button", { name: /Accept$/ }));
    await user.click(screen.getByRole("button", { name: /Apply Changes/ }));

    await waitFor(() =>
      expect(updateQuizExclusions).toHaveBeenCalledWith("s5", [
        { word: "dropped", kind: "cloze", index: 0 },
      ]),
    );
  });

  it("does not replace a changed candidate when it is rejected", async () => {
    const { generateVocabSynonym, replaceQuizQuestion, validateQuizMaterial } = await import("../services/database");
    (validateQuizMaterial as ReturnType<typeof vi.fn>).mockResolvedValue([
      { word: "alpha", kind: "synonym", poolIndex: 0, status: "suspicious", reason: "too obvious" },
    ]);
    (generateVocabSynonym as ReturnType<typeof vi.fn>).mockResolvedValue([
      { word: "alpha", synonym: "new match", distractors: ["new miss"] },
    ]);

    setStories([storyWithFullSynonymMaterial]);
    render(<TeacherQuizReviewPage />);
    const user = userEvent.setup();
    await screen.findByText("Changed review");
    await user.click(screen.getByRole("button", { name: /Validate Questions/ }));
    await screen.findByText(/too obvious/);
    await user.click(screen.getByRole("button", { name: /Update Questions/ }));

    const newLine = await screen.findByText(/new match/);
    const row = newLine.closest(".tqr-pending-change");
    expect(row).not.toBeNull();
    await user.click(within(row as HTMLElement).getByRole("button", { name: /Reject$/ }));
    await user.click(screen.getByRole("button", { name: /Apply Changes/ }));

    await waitFor(() => expect(replaceQuizQuestion).not.toHaveBeenCalled());
  });

  it("does not update exclusions for a removed candidate when it is rejected", async () => {
    const { generateVocabSynonym, updateQuizExclusions } = await import("../services/database");
    (generateVocabSynonym as ReturnType<typeof vi.fn>).mockResolvedValue([]);

    setStories([storyWithDroppedSnapshot]);
    render(<TeacherQuizReviewPage />);
    const user = userEvent.setup();
    await screen.findByText("Removed review");
    await user.click(screen.getByRole("button", { name: /Generate Questions/ }));

    const removedLine = await screen.findByText(/other choice/);
    const row = removedLine.closest(".tqr-pending-change");
    expect(row).not.toBeNull();
    await user.click(within(row as HTMLElement).getByRole("button", { name: /Reject$/ }));
    await user.click(screen.getByRole("button", { name: /Apply Changes/ }));

    await waitFor(() => expect(updateQuizExclusions).not.toHaveBeenCalled());
  });

  it("Accept All decides every still-pending candidate at once", async () => {
    const { generateVocabDistractors, generateVocabCloze } = await import("../services/database");
    (generateVocabDistractors as ReturnType<typeof vi.fn>).mockResolvedValue([
      { word: "知道", distractors: ["to see", "to hear", "to say"] },
    ]);
    (generateVocabCloze as ReturnType<typeof vi.fn>).mockResolvedValue([
      { word: "知道", sentence: "我不知道。", distractors: ["認識"] },
    ]);

    setStories([storyWithNoMaterial]);
    render(<TeacherQuizReviewPage />);
    const user = userEvent.setup();
    await screen.findByText("知道");
    await user.click(screen.getByRole("button", { name: /Generate Questions/ }));
    await screen.findByText(/New distractors/);
    await screen.findByText("我不＿＿＿。");

    await user.click(screen.getByRole("button", { name: /Accept All/ }));

    const acceptedTags = await screen.findAllByText(/Added/);
    expect(acceptedTags).toHaveLength(2);
    expect(screen.getByRole("button", { name: /Apply Changes/ })).not.toBeDisabled();
  });

  it("a rejected candidate is discarded, not persisted, when Apply runs", async () => {
    const { generateVocabDistractors, generateVocabCloze, generateVocabSynonym, updateVocabularyDistractors } = await import("../services/database");
    (generateVocabDistractors as ReturnType<typeof vi.fn>).mockResolvedValue([
      { word: "知道", distractors: ["to see", "to hear", "to say"] },
    ]);
    (generateVocabCloze as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    (generateVocabSynonym as ReturnType<typeof vi.fn>).mockResolvedValue([]);

    setStories([storyWithNoMaterial]);
    render(<TeacherQuizReviewPage />);
    const user = userEvent.setup();
    await screen.findByText("知道");
    await user.click(screen.getByRole("button", { name: /Generate Questions/ }));
    await screen.findByText(/New distractors/);

    await user.click(screen.getByRole("button", { name: /Reject$/ }));
    expect(await screen.findByText(/Discarded/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Apply Changes/ }));
    expect(updateVocabularyDistractors).not.toHaveBeenCalled();
  });

  it("regenerates an under-cap suspicious question once as a replacement, not again as a top-up", async () => {
    const {
      generateVocabDistractors,
      generateVocabCloze,
      generateVocabSynonym,
      replaceQuizQuestion,
      updateVocabularySynonym,
      validateQuizMaterial,
    } = await import("../services/database");
    const underCapStory: CustomTeacherStory = {
      ...storyWithNoMaterial,
      id: "s-under-cap",
      title: "Under-cap review",
      frames: [{
        ...storyWithNoMaterial.frames[0],
        vocabularySynonym: JSON.stringify([[
          { synonym: "old match", distractors: ["old miss"] },
        ]]),
      }],
    };
    (validateQuizMaterial as ReturnType<typeof vi.fn>).mockResolvedValue([
      { word: "知道", kind: "synonym", poolIndex: 0, status: "suspicious", reason: "duplicate answer" },
    ]);
    (generateVocabDistractors as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    (generateVocabCloze as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    (generateVocabSynonym as ReturnType<typeof vi.fn>).mockResolvedValue([
      { word: "知道", synonym: "new match", distractors: ["new miss"] },
    ]);

    setStories([underCapStory]);
    render(<TeacherQuizReviewPage />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Validate Questions/ }));
    await user.click(await screen.findByRole("button", { name: /Update Questions/ }));

    expect(await screen.findAllByText(/new match/)).toHaveLength(1);
    expect(screen.queryByText(/New distractors/)).not.toBeInTheDocument();
    expect(generateVocabSynonym).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: /Update Questions/ })).not.toBeInTheDocument();

    const row = screen.getByText(/new match/).closest(".tqr-pending-change");
    await user.click(within(row as HTMLElement).getByRole("button", { name: /Accept$/ }));
    await user.click(screen.getByRole("button", { name: /Apply Changes/ }));

    expect(updateVocabularySynonym).not.toHaveBeenCalled();
    expect(replaceQuizQuestion).toHaveBeenCalledWith(
      "s-under-cap",
      0,
      0,
      "synonym",
      0,
      { synonym: "new match", distractors: ["new miss"] },
    );
  });

  it("stages a repeated vocabulary word only once across scenes", async () => {
    const { generateVocabDistractors, generateVocabCloze, generateVocabSynonym } = await import("../services/database");
    const repeatedWordStory: CustomTeacherStory = {
      ...storyWithNoMaterial,
      id: "s-repeated",
      frames: [
        storyWithNoMaterial.frames[0],
        { ...storyWithNoMaterial.frames[0], imageUrl: "second" },
      ],
    };
    (generateVocabDistractors as ReturnType<typeof vi.fn>).mockResolvedValue([
      { word: "知道", distractors: ["to see", "to hear"] },
    ]);
    (generateVocabCloze as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    (generateVocabSynonym as ReturnType<typeof vi.fn>).mockResolvedValue([]);

    setStories([repeatedWordStory]);
    render(<TeacherQuizReviewPage />);
    await userEvent.setup().click(await screen.findByRole("button", { name: /Generate Questions/ }));

    expect(await screen.findAllByText(/New distractors/)).toHaveLength(1);
    expect(generateVocabDistractors).toHaveBeenCalledWith([
      expect.objectContaining({ word: "知道" }),
    ]);
  });
});
