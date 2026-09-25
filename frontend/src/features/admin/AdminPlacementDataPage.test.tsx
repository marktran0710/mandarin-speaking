import { render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import AdminPlacementDataPage from "./AdminPlacementDataPage";

vi.mock("../../shared/api/placement-test", () => ({
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
}));

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
});
