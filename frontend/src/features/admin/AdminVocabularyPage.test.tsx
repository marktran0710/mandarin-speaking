import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AdminVocabularyPage from "./AdminVocabularyPage";
import { createQuizVocabularyWord, deleteQuizVocabularyWord, listVocabularyStories, updateQuizVocabularyWord, updateVocabularyMetadata } from "../../services/api/vocabulary";
import type { StoredCustomStory } from "../../services/api/stories-submissions";
import type { VocabAssessmentQuestion } from "@entities/vocabulary";

vi.mock("../../services/api/vocabulary", () => ({ listVocabularyStories: vi.fn(), updateVocabularyMetadata: vi.fn(), createQuizVocabularyWord: vi.fn(), updateQuizVocabularyWord: vi.fn(), deleteQuizVocabularyWord: vi.fn() }));
const stories: StoredCustomStory[] = [
  { id: "s5", title: "我的房間", lessonNumber: 5, lessonSubOrder: 3, frames: [{ imageUrl: "", prompt: "", vocabulary: "桌子", vocabularyPinyin: "zhuō zǐ", vocabularyTranslation: "table", vocabularyPos: "N", suggestedAnswer: "房間裡有桌子。" }] },
  { id: "s6", title: "運動", lessonNumber: 6, frames: [{ imageUrl: "", prompt: "", vocabulary: "游泳", vocabularyPinyin: "yóuyǒng", vocabularyTranslation: "swim", vocabularyPos: "V" }] },
];
const quizAssessment = (wordId: string, targetWord: string, meaning: string): VocabAssessmentQuestion[] => [
  { questionId: `${wordId}_R1`, wordId, targetWord, pinyin: "pinyin", pos: "N", simpleEnglishMeaning: meaning, round: 1, tier: "tier1", questionType: "basic_meaning_mcq", answerFormat: "single_choice", prompt: `Round 1 prompt ${wordId}`, options: [meaning, "book", "door", "window"], correctAnswer: meaning, acceptedAnswers: [meaning], explanation: "Round 1 explanation" },
  { questionId: `${wordId}_R2`, wordId, targetWord, pinyin: "pinyin", pos: "N", simpleEnglishMeaning: meaning, round: 2, tier: "tier2", questionType: "character_to_pinyin_typing", answerFormat: "free_text", prompt: `Round 2 prompt ${wordId}`, options: [], correctAnswer: "pinyin", acceptedAnswers: ["pinyin"], explanation: "Round 2 explanation" },
  { questionId: `${wordId}_R3`, wordId, targetWord, pinyin: "pinyin", pos: "N", simpleEnglishMeaning: meaning, round: 3, tier: "tier3", questionType: "context_cloze_mcq", answerFormat: "single_choice", prompt: `Round 3 prompt ${wordId}`, options: [targetWord, "書", "門", "窗戶"], correctAnswer: targetWord, acceptedAnswers: [targetWord], explanation: "Round 3 explanation" },
];
beforeEach(() => {
  vi.mocked(listVocabularyStories).mockReset().mockResolvedValue(structuredClone(stories));
  vi.mocked(updateVocabularyMetadata).mockReset();
  vi.mocked(createQuizVocabularyWord).mockReset();
  vi.mocked(updateQuizVocabularyWord).mockReset();
  vi.mocked(deleteQuizVocabularyWord).mockReset();
});

describe("Admin vocabulary page", () => {
  it("makes the unified vocabulary and questions import visible", async () => {
    const user = userEvent.setup();
    render(<AdminVocabularyPage />);
    expect(await screen.findByRole("heading", { name: "Vocabulary and questions use one source" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Import vocabulary + questions" }));
    expect(screen.getByRole("dialog", { name: "Import vocabulary + questions" })).toBeInTheDocument();
    expect(screen.getByText("Download the standard XLSX template")).toBeInTheDocument();
  });

  it("includes stories without lesson metadata in the unassigned filter", async () => {
    vi.mocked(listVocabularyStories).mockResolvedValue([{ ...stories[0], lessonNumber: undefined }]);
    const user = userEvent.setup();
    render(<AdminVocabularyPage />);
    await screen.findByRole("heading", { name: "No vocabulary found" });
    await user.selectOptions(screen.getByRole("combobox", { name: "Lesson" }), "null");
    expect(screen.getByText("1 entries / 1 unique words")).toBeInTheDocument();
    expect(within(screen.getByRole("combobox", { name: "Speaking story" })).getByRole("option", { name: stories[0].title })).toBeInTheDocument();
  });
  it("filters live Speaking entries by search and lesson", async () => {
    const user = userEvent.setup();
    render(<AdminVocabularyPage />);
    await screen.findByText("2 entries / 2 unique words");
    await user.type(screen.getByRole("searchbox"), "zhuo");
    expect(screen.getByText("1 entries / 1 unique words")).toBeInTheDocument();
    expect(screen.queryByText("Book source")).not.toBeInTheDocument();
    await user.clear(screen.getByRole("searchbox"));
    await user.selectOptions(screen.getByRole("combobox", { name: "Lesson" }), "6");
    expect(screen.queryByRole("button", { name: /Edit 桌子/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Edit 游泳/ })).toBeInTheDocument();
  });
  it("labels assessment-backed vocabulary as the quiz bank for every lesson part", async () => {
    vi.mocked(listVocabularyStories).mockResolvedValue([{
      ...stories[1], lessonSubOrder: 2,
      frames: [{ imageUrl: "", prompt: "", vocabulary: "材料用字", vocabularyPinyin: "cái liào", vocabularyTranslation: "material", vocabularyPos: "N" }],
      vocabAssessment: [
        { questionId: "l6-1-R1", wordId: "l6-1-swim", targetWord: "游泳", pinyin: "yóuyǒng", pos: "V", simpleEnglishMeaning: "swim", round: 1, tier: "tier1", questionType: "basic_meaning_mcq", answerFormat: "single_choice", prompt: "", options: [], correctAnswer: "swim", acceptedAnswers: ["swim"], explanation: "" },
        { questionId: "l6-1-R2", wordId: "l6-1-swim", targetWord: "游泳", pinyin: "yóuyǒng", pos: "V", simpleEnglishMeaning: "swim", round: 2, tier: "tier2", questionType: "character_to_pinyin_typing", answerFormat: "free_text", prompt: "", options: [], correctAnswer: "yóuyǒng", acceptedAnswers: ["yóuyǒng"], explanation: "" },
        { questionId: "l6-1-R3", wordId: "l6-1-swim", targetWord: "游泳", pinyin: "yóuyǒng", pos: "V", simpleEnglishMeaning: "swim", round: 3, tier: "tier3", questionType: "context_cloze_mcq", answerFormat: "single_choice", prompt: "", options: ["游泳", "跑", "看", "吃"], correctAnswer: "游泳", acceptedAnswers: ["游泳"], explanation: "" },
      ],
    }]);
    const user = userEvent.setup();
    render(<AdminVocabularyPage />);
    await screen.findByText("1 entries / 1 unique words");
    await user.selectOptions(screen.getByRole("combobox", { name: "Lesson" }), "6");
    expect(screen.getByText("游泳")).toBeInTheDocument();
    expect(screen.getByText((_, element) => element?.tagName === "SMALL" && element.textContent === "6-2 / Quiz bank")).toBeInTheDocument();
    expect(screen.queryByText("材料用字")).not.toBeInTheDocument();
  });
  it("creates a quiz word with all three round questions", async () => {
    const quizStory: StoredCustomStory = { ...stories[0], id: "s5-create", title: "Quiz room", vocabAssessment: [] };
    const saved = { ...quizStory, vocabAssessment: quizAssessment("new-word", "沙發", "sofa") };
    vi.mocked(listVocabularyStories).mockResolvedValue([quizStory]);
    vi.mocked(createQuizVocabularyWord).mockResolvedValue(saved);
    const user = userEvent.setup();
    render(<AdminVocabularyPage />);
    await screen.findByRole("heading", { name: "No vocabulary found" });
    await user.selectOptions(screen.getByRole("combobox", { name: "Speaking story" }), "s5-create");
    await user.click(screen.getByRole("button", { name: "Add quiz word" }));
    const dialog = screen.getByRole("dialog", { name: "Add quiz vocabulary" });
    await user.type(within(dialog).getByRole("textbox", { name: "Chinese word" }), "沙發");
    await user.type(within(dialog).getByRole("textbox", { name: "Pinyin" }), "shafa");
    await user.type(within(dialog).getByRole("textbox", { name: "Meaning (English)" }), "sofa");
    await user.type(within(dialog).getByRole("textbox", { name: "Part of speech" }), "N");
    for (const [round, prompt, options, answer] of [
      ["Round 1", "What does 沙發 mean?", "sofa\nbook\ndoor\nwindow", "sofa"],
      ["Round 2", "Type the pinyin", "", "shafa"],
      ["Round 3", "Complete: ___", "沙發\n床\n門\n窗戶", "沙發"],
    ] as const) {
      await user.type(within(dialog).getByRole("textbox", { name: `${round} prompt` }), prompt);
      if (round !== "Round 2") {
        const optionsInput = within(dialog).getByRole("textbox", { name: `${round} options` });
        await user.clear(optionsInput);
        await user.type(optionsInput, options);
      }
      await user.type(within(dialog).getByRole("textbox", { name: `${round} correct answer` }), answer);
      await user.type(within(dialog).getByRole("textbox", { name: `${round} accepted answers` }), answer);
      await user.type(within(dialog).getByRole("textbox", { name: `${round} explanation` }), `${round} explanation`);
    }
    await user.click(within(dialog).getByRole("button", { name: "Add word" }));
    await screen.findByText("Quiz vocabulary added.", { exact: true });
    expect(createQuizVocabularyWord).toHaveBeenCalledWith("s5-create", expect.objectContaining({ targetWord: "沙發", questions: expect.arrayContaining([expect.objectContaining({ round: 1, correctAnswer: "sofa" }), expect.objectContaining({ round: 3, correctAnswer: "沙發" })]) }));
  }, 20000);
  it("updates the full quiz word and all round question data", async () => {
    const quizStory: StoredCustomStory = { ...stories[0], id: "s5-update", title: "Quiz room", vocabAssessment: quizAssessment("w1", "桌子", "table") };
    const saved = { ...quizStory, vocabAssessment: quizAssessment("w1", "書桌", "desk") };
    vi.mocked(listVocabularyStories).mockResolvedValue([quizStory]);
    vi.mocked(updateQuizVocabularyWord).mockResolvedValue(saved);
    const user = userEvent.setup();
    render(<AdminVocabularyPage />);
    await screen.findByText("1 entries / 1 unique words");
    await user.selectOptions(screen.getByRole("combobox", { name: "Speaking story" }), "s5-update");
    await user.click(screen.getByRole("button", { name: /Edit 桌子, quiz vocabulary/ }));
    const dialog = screen.getByRole("dialog", { name: "Edit quiz vocabulary: 桌子" });
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Chinese word" }), { target: { value: "書桌" } });
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Meaning (English)" }), { target: { value: "desk" } });
    await user.click(within(dialog).getByRole("button", { name: "Save quiz word" }));
    await screen.findByText("Quiz vocabulary saved. All three rounds now use the updated data.", { exact: true });
    expect(updateQuizVocabularyWord).toHaveBeenCalledWith("s5-update", "w1", expect.objectContaining({ targetWord: "書桌", simpleEnglishMeaning: "desk" }));
  });
  it("deletes a quiz word and removes it from the inventory", async () => {
    const quizStory: StoredCustomStory = { ...stories[0], id: "s5-delete", title: "Quiz room", vocabAssessment: quizAssessment("w1", "桌子", "table") };
    const saved = { ...quizStory, vocabAssessment: [] };
    vi.mocked(listVocabularyStories).mockResolvedValue([quizStory]);
    vi.mocked(deleteQuizVocabularyWord).mockResolvedValue(saved);
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const user = userEvent.setup();
    render(<AdminVocabularyPage />);
    await screen.findByText("1 entries / 1 unique words");
    await user.selectOptions(screen.getByRole("combobox", { name: "Speaking story" }), "s5-delete");
    await user.click(screen.getByRole("button", { name: "Delete 桌子, quiz vocabulary" }));
    await screen.findByRole("heading", { name: "No vocabulary found" });
    expect(deleteQuizVocabularyWord).toHaveBeenCalledWith("s5-delete", "w1", undefined);
    confirm.mockRestore();
  });
  it("saves metadata with the exact source precondition then updates the table", async () => {
    const user = userEvent.setup();
    const saved = structuredClone(stories[0]);
    saved.frames[0].vocabularyPinyin = "zhuō zi";
    vi.mocked(updateVocabularyMetadata).mockResolvedValue(saved);
    render(<AdminVocabularyPage />);
    await user.click(await screen.findByRole("button", { name: /Edit 桌子/ }));
    const dialog = screen.getByRole("dialog", { name: "Edit vocabulary: 桌子" });
    const input = within(dialog).getByRole("textbox", { name: "Pinyin" });
    await user.clear(input);
    await user.type(input, "zhuō zi");
    await user.click(within(dialog).getByRole("button", { name: "Save changes" }));
    await screen.findByText("Vocabulary saved.", { exact: true });
    expect(updateVocabularyMetadata).toHaveBeenCalledWith("s5", expect.objectContaining({
      frameIndex: 0, wordIndex: 0, tier: "easy", word: "桌子", pinyin: "zhuō zi",
      expected: { vocabulary: "桌子", pinyin: "zhuō zǐ", translation: "table", pos: "N" },
    }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByText("zhuō zi")).toBeInTheDocument();
  });
  it("retains edits after a conflict and never silently applies them", async () => {
    vi.mocked(updateVocabularyMetadata).mockRejectedValue(new Error("This vocabulary changed in another session."));
    const user = userEvent.setup();
    render(<AdminVocabularyPage />);
    await user.click(await screen.findByRole("button", { name: /Edit 桌子/ }));
    await user.type(screen.getByRole("textbox", { name: "Pinyin" }), " revised");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("another session");
    expect(screen.getByRole("textbox", { name: "Pinyin" })).toHaveValue("zhuō zǐ revised");
    expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled();
  });
  it("blocks comma values that would shift vocabulary columns", async () => {
    const user = userEvent.setup();
    render(<AdminVocabularyPage />);
    await user.click(await screen.findByRole("button", { name: /Edit 桌子/ }));
    await user.type(screen.getByRole("textbox", { name: "Meaning (English)" }), ", desk");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(screen.getByRole("alert")).toHaveTextContent("without commas");
    expect(updateVocabularyMetadata).not.toHaveBeenCalled();
  });
  it("shows that frame vocabulary has no generated quiz material", async () => {
    const user = userEvent.setup();
    render(<AdminVocabularyPage />);
    await user.click(await screen.findByRole("button", { name: "View quiz questions for 桌子" }));
    const dialog = screen.getByRole("dialog", { name: "Quiz questions: 桌子" });
    expect(within(dialog).getByRole("button", { name: "Audio not available" })).toBeDisabled();
    expect(within(dialog).getByText("Audio not available — import a clip to enable playback.")).toBeInTheDocument();
    expect(within(dialog).getByText(/No generated questions yet/)).toBeInTheDocument();
  });

  it("includes imported word audio in the vocabulary preview", async () => {
    const audioQuestions = quizAssessment("audio-word", "桌子", "table")
      .map(question => ({ ...question, audioUrl: "/uploads/audio/word.mp3" }));
    vi.mocked(listVocabularyStories).mockResolvedValue([{
      ...stories[0], id: "audio-story", vocabAssessment: audioQuestions,
    }]);
    const user = userEvent.setup();
    render(<AdminVocabularyPage />);
    await user.click(await screen.findByRole("button", { name: "View quiz questions for 桌子" }));
    const dialog = screen.getByRole("dialog", { name: "Quiz questions: 桌子" });
    expect(within(dialog).getByRole("button", { name: "Listen to word" })).toBeInTheDocument();
    expect(within(dialog).getByText("Imported model audio")).toBeInTheDocument();
  });

  it("no longer offers a practice-level filter", async () => {
    render(<AdminVocabularyPage />);
    await screen.findByText("2 entries / 2 unique words");
    expect(screen.queryByRole("combobox", { name: "Practice level" })).not.toBeInTheDocument();
  });

  it("retries loading and handles an empty database", async () => {
    vi.mocked(listVocabularyStories).mockRejectedValueOnce(new Error("Offline")).mockResolvedValueOnce([]);
    const user = userEvent.setup();
    render(<AdminVocabularyPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Offline");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findByRole("heading", { name: "No vocabulary found" });
    expect(screen.getByRole("button", { name: "Export CSV" })).toBeDisabled();
  });
  it("reloads the page data when admin refresh is requested", async () => {
    const { rerender } = render(<AdminVocabularyPage refreshKey={0} />);
    await screen.findByText("2 entries / 2 unique words");
    rerender(<AdminVocabularyPage refreshKey={1} />);
    await waitFor(() => expect(listVocabularyStories).toHaveBeenCalledTimes(2));
  });
});
