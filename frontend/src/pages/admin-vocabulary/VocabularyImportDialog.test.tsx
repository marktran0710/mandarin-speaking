import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import VocabularyImportDialog from "./VocabularyImportDialog";
import { confirmVocabularyImport, previewVocabularyImport } from "../../services/api/vocabulary";
import type { VocabularyImportPreview, VocabularyImportResult } from "../../services/api/vocabulary";

vi.mock("../../services/api/vocabulary", () => ({ previewVocabularyImport: vi.fn(), confirmVocabularyImport: vi.fn() }));

const cleanPreview: VocabularyImportPreview = {
  rows: 3,
  rowIssues: [],
  sections: [{ section: "5-1", storyId: "s5-1", storyTitle: "我的房間", found: true, newWords: 1, updatedWords: 0, questionCount: 3, issues: [] }],
};

function pickFile(input: HTMLElement, content = "a,b\n1,2") {
  const file = new File([content], "bank.csv", { type: "text/csv" });
  return userEvent.setup().upload(input, file);
}

beforeEach(() => {
  vi.mocked(previewVocabularyImport).mockReset().mockResolvedValue(cleanPreview);
  vi.mocked(confirmVocabularyImport).mockReset();
});

describe("VocabularyImportDialog", () => {
  it("shows the core import template without retired metadata columns", async () => {
    const user = userEvent.setup();
    render(<VocabularyImportDialog onClose={vi.fn()} onImported={vi.fn()} />);
    await user.click(screen.getByText("View and download the standard template"));
    expect(screen.getByRole("columnheader", { name: "Question ID" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Round" })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Skill Label" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Download sample CSV/ })).toBeInTheDocument();
  });

  it("previews on file select and shows the matched section", async () => {
    render(<VocabularyImportDialog onClose={vi.fn()} onImported={vi.fn()} />);
    await pickFile(screen.getByLabelText("Question bank CSV or XLSX file"));
    await screen.findByText("我的房間");
    expect(screen.getByText(/1 new/)).toBeInTheDocument();
    expect(previewVocabularyImport).toHaveBeenCalledTimes(1);
  });

  it("disables Confirm import while there are row-level validation issues", async () => {
    vi.mocked(previewVocabularyImport).mockResolvedValue({ rows: 3, rowIssues: ["Q1: bad round"], sections: [] });
    render(<VocabularyImportDialog onClose={vi.fn()} onImported={vi.fn()} />);
    await pickFile(screen.getByLabelText("Question bank CSV or XLSX file"));
    await screen.findByText("Q1: bad round");
    expect(screen.getByRole("button", { name: /Confirm import/ })).toBeDisabled();
  });

  it("disables Confirm import when a section's story isn't found", async () => {
    vi.mocked(previewVocabularyImport).mockResolvedValue({
      rows: 3, rowIssues: [],
      sections: [{ section: "97-9", storyId: null, storyTitle: null, found: false, error: "No existing story is assigned to lesson part 97-9.", newWords: 0, updatedWords: 0, questionCount: 3, issues: [] }],
    });
    render(<VocabularyImportDialog onClose={vi.fn()} onImported={vi.fn()} />);
    await pickFile(screen.getByLabelText("Question bank CSV or XLSX file"));
    await screen.findByText(/No existing story is assigned/);
    expect(screen.getByRole("button", { name: /Confirm import/ })).toBeDisabled();
  });

  it("confirms the import and reports the result, calling onImported", async () => {
    const result: VocabularyImportResult = { published: [{ section: "5-1", storyId: "s5-1", storyTitle: "我的房間", questionCount: 3 }] };
    vi.mocked(confirmVocabularyImport).mockResolvedValue(result);
    const onImported = vi.fn();
    const user = userEvent.setup();
    render(<VocabularyImportDialog onClose={vi.fn()} onImported={onImported} />);
    await pickFile(screen.getByLabelText("Question bank CSV or XLSX file"));
    await screen.findByText("我的房間");
    await user.click(screen.getByRole("button", { name: /Confirm import/ }));
    await waitFor(() => expect(screen.getByText("Imported.")).toBeInTheDocument());
    expect(screen.getByText(/我的房間 \(5-1\): 3 questions/)).toBeInTheDocument();
    expect(onImported).toHaveBeenCalledTimes(1);
  });

  it("shows an error message when confirm fails", async () => {
    vi.mocked(confirmVocabularyImport).mockRejectedValue(new Error("5-1 would fail validation after merge"));
    const user = userEvent.setup();
    render(<VocabularyImportDialog onClose={vi.fn()} onImported={vi.fn()} />);
    await pickFile(screen.getByLabelText("Question bank CSV or XLSX file"));
    await screen.findByText("我的房間");
    await user.click(screen.getByRole("button", { name: /Confirm import/ }));
    await screen.findByRole("alert");
    expect(screen.getByRole("alert")).toHaveTextContent("5-1 would fail validation after merge");
  });
});
