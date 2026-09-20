import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TeacherQuizReviewPage from "./TeacherQuizReviewPage";
import { buildMaterialSnapshot } from "../utils/quizMaterialDiff";
import { storyToTopic, type CustomTeacherStory } from "../utils/teacherStories";

const story = {
  id: "s1",
  title: "測試故事",
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
    approveQuizMaterial: vi.fn(async () => {}),
    saveQuizPendingApprovals: vi.fn(async () => {}),
    replaceQuizQuestion: vi.fn(async () => {}),
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

    expect((await screen.findAllByText("知道")).length).toBeGreaterThan(0);
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

    await screen.findAllByText("知道");
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

  it("bulk-uploads quiz questions from a teacher-authored CSV, with no AI involved", async () => {
    const { updateVocabularyDistractors, updateVocabularySynonym } = await import("../services/database");
    const user = userEvent.setup();
    render(<TeacherQuizReviewPage />);
    await screen.findByText("測試故事");

    await user.click(screen.getByRole("button", { name: /Upload Questions|上傳題目/ }));
    const input = screen.getByTestId("tqr-upload-input") as HTMLInputElement;
    const csv = [
      "word,kind,text,distractors",
      "知道,distractors,,see;hear;say",
      "not-a-real-word,synonym,foo,bar",
      "知道,cloze,a sentence without the word,bar",
    ].join("\n");
    const file = new File([csv], "quiz.csv", { type: "text/csv" });
    await user.upload(input, file);

    await waitFor(() =>
      expect(updateVocabularyDistractors).toHaveBeenCalledWith("s1", [
        { frameIndex: 0, wordIndex: 0, distractors: ["see", "hear", "say"] },
      ]),
    );
    expect(updateVocabularySynonym).not.toHaveBeenCalled();
    expect(await screen.findByText(/Added 1 distractor set/)).toBeInTheDocument();
    expect(screen.getByText(/Not found in this story: not-a-real-word/)).toBeInTheDocument();
    expect(screen.getByText(/Skipped 1 row: row 4 \(知道\/cloze\): cloze sentence doesn't contain the word/)).toBeInTheDocument();
  });

  it("notes when the server added fewer items than the CSV attempted (dedup or pool cap)", async () => {
    const { updateVocabularyDistractors } = await import("../services/database");
    // The upload asks for 3 new distractors, but the server's merge (top-up
    // + dedupe + cap) only lands 1 — simulated here by having the mocked
    // PATCH call itself update mockStories to that smaller real outcome,
    // the way the real endpoint's response would.
    (updateVocabularyDistractors as ReturnType<typeof vi.fn>).mockImplementationOnce(async () => {
      setStories([
        {
          ...story,
          frames: [{ ...story.frames[0], vocabularyDistractors: JSON.stringify([["see"], []]) }],
        },
      ]);
    });

    const user = userEvent.setup();
    render(<TeacherQuizReviewPage />);
    await screen.findByText("測試故事");

    await user.click(screen.getByRole("button", { name: /Upload Questions|上傳題目/ }));
    const input = screen.getByTestId("tqr-upload-input") as HTMLInputElement;
    const file = new File(["word,kind,text,distractors\n知道,distractors,,see;hear;say"], "quiz.csv", { type: "text/csv" });
    await user.upload(input, file);

    expect(
      await screen.findByText(/Note: not everything uploaded for 知道 may have been added/),
    ).toBeInTheDocument();
  });

  it("groups stories by lesson and only shows the selected lesson's story", async () => {
    setStories([story, storyLesson7]);
    render(<TeacherQuizReviewPage />);

    // Defaults to the lowest numbered lesson (5).
    expect((await screen.findAllByText("知道")).length).toBeGreaterThan(0);
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
    expect((await screen.findAllByText("知道")).length).toBeGreaterThan(0);

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

    expect((await screen.findAllByText("知道")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("New").length).toBeGreaterThan(0);
  });

  it("shows no diff badges when the story has never been saved before", async () => {
    render(<TeacherQuizReviewPage />);
    expect((await screen.findAllByText("知道")).length).toBeGreaterThan(0);
    expect(screen.queryByText("New")).not.toBeInTheDocument();
    expect(screen.queryByText("Changed")).not.toBeInTheDocument();
  });

  it("exports a story's current marks as a downloadable JSON file", async () => {
    const createObjectURL = vi.fn((_blob: Blob) => "blob:mock");
    const revokeObjectURL = vi.fn((_url: string) => {});
    URL.createObjectURL = createObjectURL;
    URL.revokeObjectURL = revokeObjectURL;
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    render(<TeacherQuizReviewPage />);
    await screen.findAllByText("知道");
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
    await screen.findAllByText("知道");

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
    await screen.findAllByText("知道");

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
    await screen.findAllByText("知道");

    await user.click(screen.getByText("More"));
    await user.click(screen.getByRole("button", { name: /Import|匯入/ }));
    const input = screen.getByTestId("tqr-import-input") as HTMLInputElement;
    const file = new File(["not json"], "marks.json", { type: "application/json" });
    await user.upload(input, file);

    expect(await screen.findByText(/That file is not valid JSON/)).toBeInTheDocument();
  });

  it("checkboxes are available immediately and publish only what's checked", async () => {
    const { approveQuizMaterial } = await import("../services/database");

    render(<TeacherQuizReviewPage />);
    const user = userEvent.setup();
    await screen.findAllByText("知道");

    expect(screen.queryByRole("button", { name: /Approve & Publish|核准並發佈/ })).not.toBeInTheDocument();

    // Only 知道's synonym gets checked — 一起's stays unchecked.
    const zhidaoCheckbox = screen.getByRole("checkbox", { name: "Approve synonym for 知道" });
    expect(zhidaoCheckbox).not.toBeDisabled();
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

  it("Approve all checks every question currently in the story, respecting existing exclusion marks", async () => {
    render(<TeacherQuizReviewPage />);
    const user = userEvent.setup();
    await screen.findAllByText("知道");

    await user.click(screen.getByRole("button", { name: /Approve all|核准全部/ }));

    // 知道's synonym has no exclusion mark and gets checked; 一起's synonym
    // is already excluded in the fixture (quizExclusions) so it's left out
    // of the approvable material entirely and stays unchecked.
    expect(screen.getByRole("checkbox", { name: "Approve synonym for 知道" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Approve synonym for 一起" })).not.toBeChecked();
  });

  it("editing a checked candidate persists it and keeps it checked", async () => {
    const { replaceQuizQuestion } = await import("../services/database");

    render(<TeacherQuizReviewPage />);
    const user = userEvent.setup();
    await screen.findAllByText("知道");

    const checkbox = screen.getByRole("checkbox", { name: "Approve synonym for 知道" });
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
    await user.click(screen.getByRole("button", { name: /儲存Save/ }));

    expect(replaceQuizQuestion).toHaveBeenCalledWith(
      "s1",
      0,
      0,
      "synonym",
      0,
      { synonym: "明白", distractors: ["不懂"] },
    );
    // A teacher's own edit is trusted directly — no re-approval needed.
    await waitFor(() =>
      expect(screen.getByRole("checkbox", { name: "Approve synonym for 知道" })).toBeChecked(),
    );
  });

  it("lets a teacher replace the correct answer", async () => {
    const { replaceQuizQuestion } = await import("../services/database");

    render(<TeacherQuizReviewPage />);
    const user = userEvent.setup();
    await screen.findByText("測試故事");
    await user.click(screen.getAllByRole("button", { name: /Edit answer|編輯答案/ })[0]);

    const answerInput = screen.getByLabelText(/Correct answer/);
    await user.clear(answerInput);
    await user.type(answerInput, "understand");
    await user.click(screen.getByRole("button", { name: /儲存Save/ }));

    expect(replaceQuizQuestion).toHaveBeenCalledWith(
      "s1", 0, 0, "translation", undefined, "understand", "vocabularyTranslation",
    );
  });
});

