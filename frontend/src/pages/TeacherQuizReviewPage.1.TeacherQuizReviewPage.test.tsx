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

    // Word and individual AI-question marks use separate controls. The
    // existing synonym mark is preserved while a word mark is added.
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

  it("confirms and marks one AI question for deletion without marking another", async () => {
    const { updateQuizExclusions } = await import("../services/database");
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    const user = userEvent.setup();
    render(<TeacherQuizReviewPage />);

    await screen.findByText("知道");
    const deleteZhidao = screen.getByRole("button", {
      name: "Delete synonym question for 知道",
    });
    const deleteYiQi = screen.getByRole("button", {
      name: "Restore synonym question for 一起",
    });

    await user.click(deleteZhidao);

    expect(confirmSpy).toHaveBeenCalledWith(
      "Delete this synonym question for 知道? You can restore it before saving.",
    );
    expect(deleteZhidao).toHaveAttribute("aria-pressed", "true");
    expect(deleteYiQi).toHaveAttribute("aria-pressed", "true");

    await user.click(screen.getByRole("button", { name: /Save marks|儲存標記/ }));
    expect(updateQuizExclusions).toHaveBeenCalledWith(
      "s1",
      expect.arrayContaining([
        { word: "一起", kind: "synonym", index: 0 },
        { word: "知道", kind: "synonym", index: 0 },
      ]),
      expect.anything(),
    );

    confirmSpy.mockRestore();
  });

  it("shows one cloze/synonym row and the built-in pinyin/reverse previews per word", async () => {
    setStories([
      {
        ...story,
        frames: [
          {
            ...story.frames[0],
            vocabularyCloze: JSON.stringify([
              [
                { sentence: "我知道了。", distractors: ["不知道"] },
                { sentence: "他知道答案。", distractors: ["不懂"] },
              ],
              [],
            ]),
            vocabularySynonym: JSON.stringify([
              [
                { synonym: "曉得", distractors: ["不懂"] },
                { synonym: "明白", distractors: ["糊塗"] },
              ],
              [{ synonym: "共同", distractors: ["分開"] }],
            ]),
          },
        ],
      },
    ]);
    const { container } = render(<TeacherQuizReviewPage />);
    await screen.findByText("測試故事");

    const kinds = Array.from(container.querySelectorAll(".tqr-qkind"))
      .map((element) => element.textContent ?? "");
    expect(kinds.filter((kind) => kind.includes("Cloze"))).toHaveLength(1);
    expect(kinds.filter((kind) => kind.includes("Synonym"))).toHaveLength(2);
    expect(kinds.filter((kind) => kind.includes("Pinyin"))).toHaveLength(2);
    expect(kinds.filter((kind) => kind.includes("Reverse translation"))).toHaveLength(2);
    expect(screen.queryByText("Built-in")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Delete pinyin question/ })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: /Delete reverse question/ })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: /編輯.*Edit/ }).length).toBeGreaterThanOrEqual(8);
  });

  it("can exclude a built-in question without affecting the other built-in type", async () => {
    setStories([story]);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    const user = userEvent.setup();
    render(<TeacherQuizReviewPage />);
    await screen.findByText("測試故事");

    await user.click(screen.getByRole("button", { name: "Delete pinyin question for 知道" }));

    expect(screen.getByRole("button", { name: "Restore pinyin question for 知道" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete reverse question for 知道" })).toBeInTheDocument();
    confirmSpy.mockRestore();
  });

  it("adds a missing cloze question from the word toolbar", async () => {
    const { updateVocabularyCloze } = await import("../services/database");
    const user = userEvent.setup();
    render(<TeacherQuizReviewPage />);
    await screen.findByText("測試故事");

    await user.click(screen.getByRole("button", { name: "Add question for 知道" }));
    await user.selectOptions(screen.getByLabelText(/Question type/), "cloze");
    await user.type(screen.getByLabelText(/must include the word/), "我知道答案。");
    await user.type(screen.getByLabelText(/Wrong options/), "不懂");
    expect(screen.getByLabelText(/must include the word/)).toHaveValue("我知道答案。");
    expect(screen.getByLabelText(/Wrong options/)).toHaveValue("不懂");

    const addForm = document.querySelector(".tqr-add-form");
    expect(addForm).not.toBeNull();
    await user.click(within(addForm as HTMLElement).getByRole("button", { name: /Add question/ }));

    await waitFor(() =>
      expect(updateVocabularyCloze).toHaveBeenCalledWith("s1", [
        { frameIndex: 0, wordIndex: 0, candidates: [{ sentence: "我知道答案。", distractors: ["不懂"] }] },
      ]),
    );
    expect(screen.getByText("我＿＿＿答案。")).toBeInTheDocument();
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

