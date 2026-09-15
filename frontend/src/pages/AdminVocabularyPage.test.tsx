import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AdminVocabularyPage from "./AdminVocabularyPage";
import { listVocabularyStories, updateVocabularyMetadata } from "../services/api/vocabulary";
import type { StoredCustomStory } from "../services/api/stories-submissions";

vi.mock("../services/api/vocabulary", () => ({ listVocabularyStories: vi.fn(), updateVocabularyMetadata: vi.fn() }));
const stories: StoredCustomStory[] = [
  { id: "s5", title: "我的房間", lessonNumber: 5, lessonSubOrder: 3, frames: [{ imageUrl: "", prompt: "", vocabulary: "桌子", vocabularyPinyin: "zhuō zǐ", vocabularyTranslation: "table", vocabularyPos: "N", suggestedAnswer: "房間裡有桌子。" }] },
  { id: "s6", title: "運動", lessonNumber: 6, frames: [{ imageUrl: "", prompt: "", vocabulary: "游泳", vocabularyPinyin: "yóuyǒng", vocabularyTranslation: "swim", vocabularyPos: "V" }] },
];
beforeEach(() => { vi.mocked(listVocabularyStories).mockReset().mockResolvedValue(structuredClone(stories)); vi.mocked(updateVocabularyMetadata).mockReset(); });

describe("Admin vocabulary page", () => {
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
    expect(screen.getByText("Modern Chinese 1, p. 122")).toBeInTheDocument();
    await user.clear(screen.getByRole("searchbox"));
    await user.selectOptions(screen.getByRole("combobox", { name: "Lesson" }), "6");
    expect(screen.queryByRole("button", { name: /Edit 桌子/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Edit 游泳/ })).toBeInTheDocument();
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
    await screen.findByText("Vocabulary saved. Quiz publication unchanged.");
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
  it("shows every question form of a word — the three rounds plus available practice types", async () => {
    const user = userEvent.setup();
    render(<AdminVocabularyPage />);
    await user.click(await screen.findByRole("button", { name: "View quiz questions for 桌子" }));
    const dialog = screen.getByRole("dialog", { name: "Quiz questions: 桌子" });
    // The three graded rounds are always enumerated for a glossed word.
    expect(within(dialog).getByText("Round 1")).toBeInTheDocument();
    expect(within(dialog).getByText("Round 2")).toBeInTheDocument();
    expect(within(dialog).getByText("Round 3")).toBeInTheDocument();
    // Extra practice types the word's data supports (meaning MCQ + part of speech).
    expect(within(dialog).getByText("Part of speech")).toBeInTheDocument();
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
