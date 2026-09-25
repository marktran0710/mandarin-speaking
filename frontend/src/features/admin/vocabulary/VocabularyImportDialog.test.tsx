import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import VocabularyImportDialog from "./VocabularyImportDialog";
import {
  confirmVocabularyImport,
  downloadVocabularyImportTemplate,
  previewVocabularyImport,
  type VocabularyImportPreview,
  type VocabularyImportResult,
} from "../../../services/api/vocabulary";

vi.mock("../../../services/api/vocabulary", () => ({
  previewVocabularyImport: vi.fn(),
  confirmVocabularyImport: vi.fn(),
  downloadVocabularyImportTemplate: vi.fn(),
}));

const cleanPreview: VocabularyImportPreview = {
  mode: "replace_lesson",
  rows: 3,
  rowIssues: [],
  sections: [{
    section: "5-1", storyId: "s5-1", storyTitle: "Lesson 5-1", found: true,
    newWords: 1, updatedWords: 0, removedWords: 0, preservedAudio: 0,
    missingAudio: 1, questionCount: 3, issues: [],
  }],
  newWords: 1,
  updatedWords: 0,
  removedWords: 0,
  preservedAudio: 0,
  missingAudio: 1,
};

function uploadFile(input: HTMLElement) {
  return userEvent.setup().upload(input, new File(["file"], "bank.xlsx", {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  }));
}

beforeEach(() => {
  vi.mocked(previewVocabularyImport).mockReset().mockResolvedValue(cleanPreview);
  vi.mocked(confirmVocabularyImport).mockReset();
  vi.mocked(downloadVocabularyImportTemplate).mockReset().mockResolvedValue(new Blob(["xlsx"]));
});

describe("VocabularyImportDialog", () => {
  it("uses the server-owned XLSX template and does not show retired columns", async () => {
    const user = userEvent.setup();
    render(<VocabularyImportDialog onClose={vi.fn()} onImported={vi.fn()} />);
    await user.click(screen.getByText("Download the standard XLSX template"));
    expect(screen.getByRole("button", { name: /Download XLSX template/ })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Source Type" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Download XLSX template/ }));
    await waitFor(() => expect(downloadVocabularyImportTemplate).toHaveBeenCalledTimes(1));
  });

  it("previews the replacement counts and missing audio state", async () => {
    render(<VocabularyImportDialog onClose={vi.fn()} onImported={vi.fn()} />);
    await uploadFile(screen.getByLabelText("Question bank CSV or XLSX file"));
    expect(await screen.findByText(/1 new · 0 updated · 0 removed/)).toBeInTheDocument();
    expect(screen.getByText("1 word missing audio")).toBeInTheDocument();
    expect(previewVocabularyImport).toHaveBeenCalledTimes(1);
  });

  it("requires acknowledgement before removing old canonical words", async () => {
    vi.mocked(previewVocabularyImport).mockResolvedValue({
      ...cleanPreview,
      removedWords: 2,
      sections: [{ ...cleanPreview.sections[0], removedWords: 2 }],
    });
    render(<VocabularyImportDialog onClose={vi.fn()} onImported={vi.fn()} />);
    await uploadFile(screen.getByLabelText("Question bank CSV or XLSX file"));
    const confirm = await screen.findByRole("button", { name: "Confirm replace import" });
    expect(confirm).toBeDisabled();
    await userEvent.setup().click(screen.getByRole("checkbox", { name: /remove 2 old canonical words/ }));
    expect(confirm).toBeEnabled();
  });

  it("blocks confirm when row validation fails", async () => {
    vi.mocked(previewVocabularyImport).mockResolvedValue({ ...cleanPreview, rowIssues: ["Q1: bad round"], sections: [] });
    render(<VocabularyImportDialog onClose={vi.fn()} onImported={vi.fn()} />);
    await uploadFile(screen.getByLabelText("Question bank CSV or XLSX file"));
    await screen.findByText("Q1: bad round");
    expect(screen.getByRole("button", { name: "Confirm replace import" })).toBeDisabled();
  });

  it("confirms and reports replacement result", async () => {
    const result: VocabularyImportResult = {
      mode: "replace_lesson",
      published: [{
        section: "5-1", storyId: "s5-1", storyTitle: "Lesson 5-1", questionCount: 3,
        newWords: 1, updatedWords: 0, removedWords: 0, preservedAudio: 0, missingAudio: 1,
      }],
      newWords: 1, updatedWords: 0, removedWords: 0, preservedAudio: 0, missingAudio: 1,
    };
    vi.mocked(confirmVocabularyImport).mockResolvedValue(result);
    const onImported = vi.fn();
    render(<VocabularyImportDialog onClose={vi.fn()} onImported={onImported} />);
    await uploadFile(screen.getByLabelText("Question bank CSV or XLSX file"));
    await userEvent.setup().click(await screen.findByRole("button", { name: "Confirm replace import" }));
    await waitFor(() => expect(screen.getByText("Imported.")).toBeInTheDocument());
    expect(screen.getByText(/Lesson 5-1 \(5-1\): 3 questions/)).toBeInTheDocument();
    expect(onImported).toHaveBeenCalledTimes(1);
  });
});
