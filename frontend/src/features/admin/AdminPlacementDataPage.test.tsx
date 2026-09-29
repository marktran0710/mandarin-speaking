import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import AdminPlacementDataPage from "./AdminPlacementDataPage";

vi.mock("../../shared/api/placement-test", () => ({
  activatePlacementStudentAccounts: vi.fn(),
  confirmPlacementResponseImport: vi.fn(),
  downloadPlacementResponseSample: vi.fn(),
  getAdminPlacementImportResults: vi.fn().mockResolvedValue({
    available: true,
    evidenceOrigin: "synthetic",
    resolverVersion: "placement-workbook-import-v1",
    importedAt: "2026-09-25T07:46:01Z",
    modelVersions: ["format-aware-bkt-v2"],
    parameterFingerprints: ["fingerprint"],
    summary: {
      studentCount: 40,
      attemptCount: 40,
      responseCount: 1120,
      correctCount: 636,
      incorrectCount: 484,
      accuracy: 56.8,
      tier1: { responseCount: 560, correctCount: 338, incorrectCount: 222, accuracy: 60.4 },
      tier3: { responseCount: 560, correctCount: 298, incorrectCount: 262, accuracy: 53.2 },
      masteryRowCount: 1120,
      masteryStatuses: { UNASSESSED: 1120 },
    },
    students: [{
      studentId: "SIM001",
      name: "Synthetic Student 001",
      sessionId: "PLACEMENT-SIM001-V1",
      attemptId: "PLACEMENT-SIM001-V1",
      attemptStatus: "completed",
      blueprintRevision: 1,
      completedAt: "2026-09-25T07:46:01Z",
      totalQuestions: 28,
      correctCount: 20,
      totalTimeMs: 1000,
      accuracy: 71.4,
      tier1: { responseCount: 14, correctCount: 10, incorrectCount: 4, accuracy: 71.4 },
      tier3: { responseCount: 14, correctCount: 10, incorrectCount: 4, accuracy: 71.4 },
      mastery: { rowCount: 28, statuses: { UNASSESSED: 28 }, minPLearned: .17, maxPLearned: .6 },
      responses: [],
    }],
  }),
  previewPlacementResponseImport: vi.fn(),
  replacePlacementResponseImport: vi.fn(),
}));

import {
  activatePlacementStudentAccounts,
  downloadPlacementResponseSample,
  previewPlacementResponseImport,
  replacePlacementResponseImport,
} from "../../shared/api/placement-test";

describe("AdminPlacementDataPage", () => {
  it("renders the import totals and student detail control", async () => {
    render(<AdminPlacementDataPage />);

    await waitFor(() => expect(screen.getAllByText("1,120").length).toBeGreaterThan(0));
    expect(screen.getByRole("heading", { name: "40-student response view" })).toBeInTheDocument();
    expect(screen.getByText("636 correct · 484 incorrect")).toBeInTheDocument();
    expect(screen.getByText((_, element) => element?.textContent === "1 of 40 students visible")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Imported student comparison" })).toHaveClass("placement-data-student-table-wrap");
    expect(screen.getByRole("button", { name: /SIM001.*Synthetic Student 001/ })).toBeInTheDocument();
  });

  it("offers the response workbook sample and file preview", async () => {
    vi.mocked(downloadPlacementResponseSample).mockResolvedValue(new Blob(["xlsx"]));
    vi.mocked(previewPlacementResponseImport).mockResolvedValue({
      valid: true,
      filename: "responses.xlsx",
      rowIssues: [],
      studentCount: 40,
      questionCount: 28,
      responseCount: 1120,
      correctCount: 636,
      incorrectCount: 484,
      correctByMode: { tier1: 338, tier3: 298 },
      canonicalizedStoryAliases: 0,
      existingSessions: 0,
      newSessions: 40,
    });
    const user = userEvent.setup();
    render(<AdminPlacementDataPage />);

    expect(await screen.findByRole("heading", { name: "40-student response view" })).toBeInTheDocument();
    await user.click(screen.getByText("Download sample and view required format"));
    await user.click(screen.getByRole("button", { name: "Download XLSX sample" }));
    await waitFor(() => expect(downloadPlacementResponseSample).toHaveBeenCalledTimes(1));

    await user.upload(screen.getByLabelText("Placement response XLSX file"), new File(["xlsx"], "responses.xlsx"));
    expect(await screen.findByText("1,120 responses ready")).toBeInTheDocument();
  });

  it("activates login access for the imported student cohort", async () => {
    vi.mocked(activatePlacementStudentAccounts).mockResolvedValue({
      activatedAccounts: 40,
      studentIds: Array.from({ length: 40 }, (_, index) => `SIM${String(index + 1).padStart(3, "0")}`),
      testAccounts: true,
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const user = userEvent.setup();
    render(<AdminPlacementDataPage />);

    expect(await screen.findByRole("heading", { name: "Activate 40 student logins" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Shared temporary password"), "shared-login-2026");
    await user.click(screen.getByRole("button", { name: "Activate 40 logins" }));

    await waitFor(() => expect(activatePlacementStudentAccounts).toHaveBeenCalledWith("shared-login-2026"));
    expect(await screen.findByText("Activated 40 student logins. Use each student name below with the shared temporary password.")).toBeInTheDocument();
  });

  it("lets the admin delete conflicting SIM test data and re-import when a workbook is blocked", async () => {
    vi.mocked(previewPlacementResponseImport).mockResolvedValue({
      valid: false,
      filename: "responses.xlsx",
      rowIssues: ["PLACEMENT-SIM001-V1: question snapshot differs from the active blueprint"],
      studentCount: 0,
      questionCount: 0,
      responseCount: 0,
      correctCount: 0,
      incorrectCount: 0,
      correctByMode: {},
      canonicalizedStoryAliases: 0,
      existingSessions: 0,
      newSessions: 0,
    });
    vi.mocked(replacePlacementResponseImport).mockResolvedValue({
      valid: true,
      filename: "responses.xlsx",
      deletedStudents: 1,
      deletedAttempts: 1,
      deletedResponses: 2,
      studentCount: 40,
      questionCount: 28,
      responseCount: 1120,
      correctCount: 636,
      incorrectCount: 484,
      correctByMode: { tier1: 338, tier3: 298 },
      canonicalizedStoryAliases: 0,
      existingSessions: 0,
      newSessions: 40,
      createdStudents: 40,
      createdAttempts: 40,
      createdResponses: 1120,
      rebuiltStudents: 40,
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const user = userEvent.setup();
    render(<AdminPlacementDataPage />);

    expect(await screen.findByRole("heading", { name: "40-student response view" })).toBeInTheDocument();
    await user.upload(screen.getByLabelText("Placement response XLSX file"), new File(["xlsx"], "responses.xlsx"));
    expect(await screen.findByText("Import blocked")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm import" })).toBeDisabled();

    const replaceButton = screen.getByRole("button", { name: "Delete SIM test data & re-import" });
    await user.click(replaceButton);

    await waitFor(() => expect(replacePlacementResponseImport).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/Replaced data for 1 student\(s\), deleted 1 earlier attempt\(s\) and 2 response\(s\)/)).toBeInTheDocument();
  });
});
