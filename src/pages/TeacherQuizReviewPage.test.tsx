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
    expect(screen.getByText((_, element) =>
      element?.classList.contains("tqr-rail-summary") === true &&
      element.textContent?.includes("1") === true &&
      element.textContent?.includes("marked") === true,
    )).toBeInTheDocument();

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
    await userEvent.setup().click(screen.getByText("More"));
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

    await user.click(screen.getByText("More"));
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

    await user.click(screen.getByText("More"));
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

    await user.click(screen.getByText("More"));
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

    expect(screen.queryByRole("checkbox", { name: "Approve synonym for 知道" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Approve & Publish|核准並發佈/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Validate|檢查題目/ }));
    expect(await screen.findByText(/second correct answer/)).toBeInTheDocument();
    const zhidaoCheckbox = screen.getByRole("checkbox", { name: "Approve synonym for 知道" });
    expect(zhidaoCheckbox).not.toBeDisabled();
    const suspiciousCheckbox = screen
      .getAllByRole("checkbox")
      .find((checkbox) => checkbox !== zhidaoCheckbox && checkbox.getAttribute("aria-label")?.startsWith("Approve synonym"));
    expect(suspiciousCheckbox).toBeDefined();
    expect(suspiciousCheckbox!).toBeDisabled();

    // A suspicious result is never selectable for publication.

    // Only 知道's synonym gets checked — 一起's stays unchecked despite also
    // visible for correction but is not publishable.
    await user.click(zhidaoCheckbox);
    await user.click(await screen.findByRole("button", { name: /Approve & Publish|核准並發佈/ }));

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

    const synonymEdit = screen
      .getAllByRole("button", { name: /Edit|編輯/ })
      .find((button) => button.closest(".tqr-qrow")?.textContent?.includes("Synonym"));
    expect(synonymEdit).toBeDefined();
    await user.click(synonymEdit!);
    const synonymInput = screen.getByLabelText(/Synonym|同義詞/);
    await user.clear(synonymInput);
    await user.type(synonymInput, "明白");
    await user.click(screen.getByRole("button", { name: /needs re-validation|重新驗證/ }));

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
    await waitFor(() =>
      expect(screen.queryByRole("checkbox", { name: "Approve synonym for 知道" })).not.toBeInTheDocument(),
    );
  });
  it("lets a teacher replace the correct answer and invalidates the word's review", async () => {
    const { validateQuizMaterial, replaceQuizQuestion } = await import("../services/database");
    (validateQuizMaterial as ReturnType<typeof vi.fn>).mockResolvedValue([
      { word: "?仿?", kind: "translation", status: "clean", reason: "" },
      { word: "?仿?", kind: "synonym", poolIndex: 0, status: "clean", reason: "" },
    ]);

    render(<TeacherQuizReviewPage />);
    const user = userEvent.setup();
    await screen.findByText("測試故事");
    await user.click(screen.getByRole("button", { name: /Validate Questions/ }));
    await user.click(screen.getAllByRole("button", { name: /Edit answer|編輯答案/ })[0]);

    const answerInput = screen.getByLabelText(/Correct answer/);
    await user.clear(answerInput);
    await user.type(answerInput, "understand");
    await user.click(screen.getByRole("button", { name: /needs re-validation/ }));

    expect(replaceQuizQuestion).toHaveBeenCalledWith(
      "s1", 0, 0, "translation", undefined, "understand", "vocabularyTranslation",
    );
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
        vocabularyLookalike: JSON.stringify([["l1", "l2", "l3", "l4", "l5", "l6"]]),
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
      generateVocabLookalike,
      updateVocabularyDistractors,
    } = await import("../services/database");
    (generateVocabDistractors as ReturnType<typeof vi.fn>).mockResolvedValue([
      { word: "知道", distractors: ["to see", "to hear", "to say"] },
    ]);
    (generateVocabCloze as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    (generateVocabSynonym as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    (generateVocabLookalike as ReturnType<typeof vi.fn>).mockResolvedValue([]);

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

    const acceptedTags = await screen.findAllByText(/Added/);
    expect(acceptedTags).toHaveLength(2);
    expect(screen.getByRole("button", { name: /Apply Changes/ })).not.toBeDisabled();
  });

  it("a rejected candidate is discarded, not persisted, when Apply runs", async () => {
    const { generateVocabDistractors, generateVocabCloze, generateVocabSynonym, generateVocabLookalike, updateVocabularyDistractors } = await import("../services/database");
    (generateVocabDistractors as ReturnType<typeof vi.fn>).mockResolvedValue([
      { word: "知道", distractors: ["to see", "to hear", "to say"] },
    ]);
    (generateVocabCloze as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    (generateVocabSynonym as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    (generateVocabLookalike as ReturnType<typeof vi.fn>).mockResolvedValue([]);

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
      generateVocabLookalike,
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
    (generateVocabLookalike as ReturnType<typeof vi.fn>).mockResolvedValue([]);
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
    const { generateVocabDistractors, generateVocabCloze, generateVocabSynonym, generateVocabLookalike } = await import("../services/database");
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
    (generateVocabLookalike as ReturnType<typeof vi.fn>).mockResolvedValue([]);

    setStories([repeatedWordStory]);
    render(<TeacherQuizReviewPage />);
    await userEvent.setup().click(await screen.findByRole("button", { name: /Generate Questions/ }));

    expect(await screen.findAllByText(/New distractors/)).toHaveLength(1);
    expect(generateVocabDistractors).toHaveBeenCalledWith([
      expect.objectContaining({ word: "知道" }),
    ]);
  });
});
