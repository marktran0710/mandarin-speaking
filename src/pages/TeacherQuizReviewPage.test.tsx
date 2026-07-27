import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
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
    generateVocabLookalike: vi.fn(async () => []),
    updateVocabularyDistractors: vi.fn(async () => {}),
    updateVocabularyCloze: vi.fn(async () => {}),
    updateVocabularySynonym: vi.fn(async () => {}),
    updateVocabularyLookalike: vi.fn(async () => {}),
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

describe("TeacherQuizReviewPage", () => {
  it("lists quiz material, shows saved marks, and saves a new toggle with a material snapshot", async () => {
    const { updateQuizExclusions } = await import("../services/database");
    render(<TeacherQuizReviewPage />);

    expect(await screen.findByText("知道")).toBeInTheDocument();
    expect(screen.getByText(/曉得/)).toBeInTheDocument();
    expect(screen.getByText("1 marked")).toBeInTheDocument();

    // distractors/cloze/synonym no longer have their own trash button (the
    // opt-in checkbox flow governs those); "word" and "lookalike" still do.
    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: "Exclude word for 一起" }));
    await userEvent.setup().click(screen.getByRole("button", { name: /Save marks|儲存標記/ }));

    const expectedSnapshot = { easy: buildMaterialSnapshot(storyToTopic(story, "easy")) };
    expect(updateQuizExclusions).toHaveBeenCalledWith(
      "s1",
      [
        { word: "一起", kind: "synonym", index: 0 },
        { word: "一起", kind: "word" },
      ],
      expectedSnapshot,
    );
  });

  it("groups stories by lesson and only shows the selected lesson's story", async () => {
    setStories([story, storyLesson7]);
    render(<TeacherQuizReviewPage />);

    // Defaults to the lowest numbered lesson (5).
    expect(await screen.findByText("知道")).toBeInTheDocument();
    expect(screen.queryByText("茶")).not.toBeInTheDocument();

    const lessonSelect = screen.getByLabelText(/Lesson/);
    await userEvent.setup().selectOptions(lessonSelect, "7");

    expect(await screen.findByText("茶")).toBeInTheDocument();
    expect(screen.queryByText("知道")).not.toBeInTheDocument();
  });

  it("jumpToLesson deep-links straight to that lesson, overriding the default lowest-lesson pick", async () => {
    setStories([story, storyLesson7]);
    const { rerender } = render(<TeacherQuizReviewPage />);

    // Defaults to lesson 5 first.
    expect(await screen.findByText("知道")).toBeInTheDocument();

    rerender(<TeacherQuizReviewPage jumpToLesson={{ lessonNumber: 7, nonce: 1 }} />);
    expect(await screen.findByText("茶")).toBeInTheDocument();
    expect(screen.queryByText("知道")).not.toBeInTheDocument();
  });

  it("flags a word with no matching snapshot entry as new", async () => {
    setStories([
      {
        ...story,
        quizMaterialSnapshot: {
          easy: [
            {
              word: "舊詞",
              translation: "old word",
              distractors: [],
              cloze: [],
              synonym: [],
            },
          ],
        },
      },
    ]);
    render(<TeacherQuizReviewPage />);

    expect(await screen.findByText("知道")).toBeInTheDocument();
    expect(screen.getAllByText("🆕").length).toBeGreaterThan(0);
  });

  it("shows no diff badges when the story has never been saved before", async () => {
    render(<TeacherQuizReviewPage />);
    expect(await screen.findByText("知道")).toBeInTheDocument();
    expect(screen.queryByText("🆕")).not.toBeInTheDocument();
    expect(screen.queryByText("✎")).not.toBeInTheDocument();
  });

  it("exports a story's current marks as a downloadable JSON file", async () => {
    const createObjectURL = vi.fn((_blob: Blob) => "blob:mock");
    const revokeObjectURL = vi.fn((_url: string) => {});
    URL.createObjectURL = createObjectURL;
    URL.revokeObjectURL = revokeObjectURL;
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    render(<TeacherQuizReviewPage />);
    await screen.findByText("知道");
    await userEvent.setup().click(screen.getByRole("button", { name: /Export|匯出/ }));

    expect(createObjectURL).toHaveBeenCalledTimes(1);
    const blob = createObjectURL.mock.calls[0][0];
    const payload = JSON.parse(await blob.text());
    expect(payload.storyId).toBe("s1");
    expect(payload.exclusions).toEqual([{ word: "一起", kind: "synonym", index: 0 }]);

    clickSpy.mockRestore();
  });

  it("imports marks from a file, replacing the story's marks and marking it dirty", async () => {
    render(<TeacherQuizReviewPage />);
    const user = userEvent.setup();
    await screen.findByText("知道");

    await user.click(screen.getByRole("button", { name: /Import|匯入/ }));
    const input = screen.getByTestId("tqr-import-input") as HTMLInputElement;
    const file = new File(
      [JSON.stringify({ storyId: "s1", exclusions: [{ word: "知道", kind: "word" }] })],
      "marks.json",
      { type: "application/json" },
    );
    await user.upload(input, file);

    expect(await screen.findByText(/Imported 1 marks/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Save marks|儲存標記/ })).not.toBeDisabled();
  });

  it("warns when an imported file was exported from a different story", async () => {
    render(<TeacherQuizReviewPage />);
    const user = userEvent.setup();
    await screen.findByText("知道");

    await user.click(screen.getByRole("button", { name: /Import|匯入/ }));
    const input = screen.getByTestId("tqr-import-input") as HTMLInputElement;
    const file = new File(
      [JSON.stringify({ storyId: "other-story", exclusions: [] })],
      "marks.json",
      { type: "application/json" },
    );
    await user.upload(input, file);

    expect(await screen.findByText(/different story/)).toBeInTheDocument();
  });

  it("rejects an invalid marks file without crashing", async () => {
    render(<TeacherQuizReviewPage />);
    const user = userEvent.setup();
    await screen.findByText("知道");

    await user.click(screen.getByRole("button", { name: /Import|匯入/ }));
    const input = screen.getByTestId("tqr-import-input") as HTMLInputElement;
    const file = new File(["not json"], "marks.json", { type: "application/json" });
    await user.upload(input, file);

    expect(await screen.findByText(/⚠/)).toBeInTheDocument();
  });

  it("checkboxes stay disabled until Validate runs, then enable and publish only what's checked", async () => {
    const { validateQuizMaterial, approveQuizMaterial } = await import("../services/database");
    (validateQuizMaterial as ReturnType<typeof vi.fn>).mockResolvedValue([
      { word: "知道", kind: "synonym", poolIndex: 0, status: "clean", reason: "" },
      { word: "一起", kind: "synonym", poolIndex: 0, status: "suspicious", reason: "second correct answer" },
    ]);

    render(<TeacherQuizReviewPage />);
    const user = userEvent.setup();
    await screen.findByText("知道");

    const zhidaoCheckbox = screen.getByRole("checkbox", { name: "Approve synonym for 知道" });
    expect(zhidaoCheckbox).toBeDisabled();
    expect(screen.getByRole("button", { name: /Approve & Publish|核准並發佈/ })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: /Validate|檢查題目/ }));
    expect(await screen.findByText(/second correct answer/)).toBeInTheDocument();
    expect(zhidaoCheckbox).not.toBeDisabled();

    // Only 知道's synonym gets checked — 一起's stays unchecked despite also
    // having been validated (suspicious items are checkable, just not
    // auto-checked).
    await user.click(zhidaoCheckbox);
    await user.click(screen.getByRole("button", { name: /Approve & Publish|核准並發佈/ }));

    expect(approveQuizMaterial).toHaveBeenCalledTimes(1);
    const [, , material] = (approveQuizMaterial as ReturnType<typeof vi.fn>).mock.calls[0];
    const zhidaoEntry = material.find((e: { word: string }) => e.word === "知道");
    const yiqiEntry = material.find((e: { word: string }) => e.word === "一起");
    expect(zhidaoEntry.synonym).toHaveLength(1);
    expect(yiqiEntry.synonym).toHaveLength(0);
    expect(await screen.findByText("Published")).toBeInTheDocument();
  });

  it("Approve all clean checks every clean item but leaves suspicious ones alone", async () => {
    const { validateQuizMaterial } = await import("../services/database");
    (validateQuizMaterial as ReturnType<typeof vi.fn>).mockResolvedValue([
      { word: "知道", kind: "synonym", poolIndex: 0, status: "clean", reason: "" },
      { word: "一起", kind: "synonym", poolIndex: 0, status: "suspicious", reason: "second correct answer" },
    ]);

    render(<TeacherQuizReviewPage />);
    const user = userEvent.setup();
    await screen.findByText("知道");
    await user.click(screen.getByRole("button", { name: /Validate|檢查題目/ }));
    await screen.findByText(/second correct answer/);

    await user.click(screen.getByRole("button", { name: /Approve all clean|核准全部/ }));

    expect(screen.getByRole("checkbox", { name: "Approve synonym for 知道" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Approve synonym for 一起" })).not.toBeChecked();
  });

  it("editing a checked candidate persists it and resets validation + checked state", async () => {
    const { validateQuizMaterial, replaceQuizQuestion } = await import("../services/database");
    (validateQuizMaterial as ReturnType<typeof vi.fn>).mockResolvedValue([
      { word: "知道", kind: "synonym", poolIndex: 0, status: "clean", reason: "" },
    ]);

    render(<TeacherQuizReviewPage />);
    const user = userEvent.setup();
    await screen.findByText("知道");
    await user.click(screen.getByRole("button", { name: /Validate|檢查題目/ }));

    const checkbox = await screen.findByRole("checkbox", { name: "Approve synonym for 知道" });
    await user.click(checkbox);
    expect(checkbox).toBeChecked();

    await user.click(screen.getAllByRole("button", { name: /Edit|編輯/ })[0]);
    const synonymInput = screen.getByLabelText(/Synonym|同義詞/);
    await user.clear(synonymInput);
    await user.type(synonymInput, "明白");
    await user.click(screen.getByRole("button", { name: /needs re-validate|重新檢查/ }));

    expect(replaceQuizQuestion).toHaveBeenCalledWith(
      "s1",
      0,
      0,
      "synonym",
      0,
      { synonym: "明白", distractors: ["不懂"] },
    );
    // An edit invalidates the item — it must be re-Validated before it can
    // be checked again.
    expect(await screen.findByRole("checkbox", { name: "Approve synonym for 知道" })).toBeDisabled();
    expect(screen.getByRole("checkbox", { name: "Approve synonym for 知道" })).not.toBeChecked();
  });
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

  it("shows 'Generate Questions' for a story with no AI material yet, 'Update Questions' once it has some", async () => {
    setStories([storyWithNoMaterial]);
    render(<TeacherQuizReviewPage />);
    expect(await screen.findByRole("button", { name: /Generate Questions/ })).toBeInTheDocument();

    setStories([story]);
    render(<TeacherQuizReviewPage />);
    expect(await screen.findByRole("button", { name: /Update Questions/ })).toBeInTheDocument();
  });

  it("generates, reveals a new candidate, and only persists it once accepted and applied", async () => {
    const { generateVocabDistractors, updateVocabularyDistractors } = await import("../services/database");
    (generateVocabDistractors as ReturnType<typeof vi.fn>).mockResolvedValue([
      { word: "知道", distractors: ["to see", "to hear", "to say"] },
    ]);

    setStories([storyWithNoMaterial]);
    render(<TeacherQuizReviewPage />);
    const user = userEvent.setup();
    await screen.findByText("知道");

    await user.click(screen.getByRole("button", { name: /Generate Questions/ }));

    // Reveals as a 🆕 New candidate; Apply is disabled until decided.
    expect(await screen.findByText(/New distractors/)).toBeInTheDocument();
    expect(screen.getByText(/🆕 New/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Apply Changes/ })).toBeDisabled();
    expect(updateVocabularyDistractors).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /Accept$/ }));
    expect(await screen.findByText(/✓ Accepted/)).toBeInTheDocument();

    const applyButton = screen.getByRole("button", { name: /Apply Changes/ });
    expect(applyButton).not.toBeDisabled();
    await user.click(applyButton);

    expect(updateVocabularyDistractors).toHaveBeenCalledWith("s3", [
      { frameIndex: 0, wordIndex: 0, distractors: ["to see", "to hear", "to say"] },
    ]);
  });

  it("Accept All decides every still-pending candidate at once", async () => {
    const { generateVocabDistractors, generateVocabLookalike } = await import("../services/database");
    (generateVocabDistractors as ReturnType<typeof vi.fn>).mockResolvedValue([
      { word: "知道", distractors: ["to see", "to hear", "to say"] },
    ]);
    (generateVocabLookalike as ReturnType<typeof vi.fn>).mockResolvedValue([
      { word: "知道", lookalikes: ["知到"] },
    ]);

    setStories([storyWithNoMaterial]);
    render(<TeacherQuizReviewPage />);
    const user = userEvent.setup();
    await screen.findByText("知道");
    await user.click(screen.getByRole("button", { name: /Generate Questions/ }));
    await screen.findByText(/New distractors/);
    await screen.findByText(/New look-alikes/);

    await user.click(screen.getByRole("button", { name: /Accept All/ }));

    const acceptedTags = await screen.findAllByText(/✓ Accepted/);
    expect(acceptedTags).toHaveLength(2);
    expect(screen.getByRole("button", { name: /Apply Changes/ })).not.toBeDisabled();
  });

  it("a rejected candidate is discarded, not persisted, when Apply runs", async () => {
    const { generateVocabDistractors, updateVocabularyDistractors } = await import("../services/database");
    (generateVocabDistractors as ReturnType<typeof vi.fn>).mockResolvedValue([
      { word: "知道", distractors: ["to see", "to hear", "to say"] },
    ]);

    setStories([storyWithNoMaterial]);
    render(<TeacherQuizReviewPage />);
    const user = userEvent.setup();
    await screen.findByText("知道");
    await user.click(screen.getByRole("button", { name: /Generate Questions/ }));
    await screen.findByText(/New distractors/);

    await user.click(screen.getByRole("button", { name: /Reject$/ }));
    expect(await screen.findByText(/✕ Rejected/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Apply Changes/ }));
    expect(updateVocabularyDistractors).not.toHaveBeenCalled();
  });
});
