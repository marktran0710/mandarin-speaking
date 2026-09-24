import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import VocabularyAudioImportDialog from "./VocabularyAudioImportDialog";
import {
  confirmVocabularyAudioImport,
  previewVocabularyAudioImport,
  type VocabularyAudioImportPreview,
} from "../../services/api/vocabulary";

vi.mock("../../services/api/vocabulary", () => ({
  previewVocabularyAudioImport: vi.fn(),
  confirmVocabularyAudioImport: vi.fn(),
}));

const cleanPreview: VocabularyAudioImportPreview = {
  files: 2,
  matched: [{ filename: "C5-5-1-I1-W001.mp3", wordKey: "C5-5-1-I1-W001", storyId: "s5", storyTitle: "Lesson 5-1", bytes: 100 }],
  unmatched: ["unknown.mp3"],
  issues: [],
};

beforeEach(() => {
  vi.mocked(previewVocabularyAudioImport).mockReset().mockResolvedValue(cleanPreview);
  vi.mocked(confirmVocabularyAudioImport).mockReset();
});

describe("VocabularyAudioImportDialog", () => {
  it("explains the Word Key ZIP convention and previews matches", async () => {
    const user = userEvent.setup();
    render(<VocabularyAudioImportDialog onClose={vi.fn()} onImported={vi.fn()} />);
    expect(screen.getByText(/Name each file exactly like its Word Key/)).toBeInTheDocument();
    await user.upload(screen.getByLabelText("Vocabulary audio ZIP file"), new File(["zip"], "vocabulary-audio.zip", { type: "application/zip" }));
    await screen.findByText((_, element) => element?.tagName === "P" && element.textContent?.includes("matched of 2 audio files") === true);
    expect(screen.getByText("C5-5-1-I1-W001")).toBeInTheDocument();
    expect(screen.getByText("unknown.mp3")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm audio import" })).toBeEnabled();
  });

  it("confirms the ZIP and reports the number of updated words", async () => {
    vi.mocked(confirmVocabularyAudioImport).mockResolvedValue({ files: 1, updated: 1, unmatched: [], stories: ["Lesson 5-1"] });
    const onImported = vi.fn();
    const user = userEvent.setup();
    render(<VocabularyAudioImportDialog onClose={vi.fn()} onImported={onImported} />);
    await user.upload(screen.getByLabelText("Vocabulary audio ZIP file"), new File(["zip"], "vocabulary-audio.zip", { type: "application/zip" }));
    await user.click(await screen.findByRole("button", { name: "Confirm audio import" }));
    await waitFor(() => expect(screen.getByText(/Audio imported/)).toBeInTheDocument());
    expect(onImported).toHaveBeenCalledTimes(1);
    expect(confirmVocabularyAudioImport).toHaveBeenCalledTimes(1);
  });
});
