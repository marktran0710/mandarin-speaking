import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { getResearchAdminSummary } = vi.hoisted(() => ({ getResearchAdminSummary: vi.fn() }));

vi.mock("../../services/api/research-admin", () => ({ getResearchAdminSummary }));

import AdminResearchPage from "./AdminResearchPage";

const SUMMARY = {
  studyId: "study-1",
  name: "BKT x SM-2 Study",
  status: "active",
  participants: { active: 58, total: 60 },
  assignmentBalance: { C: 10, B: 10, S: 10, BS: 10 },
  totalAssignments: 40,
  fidelity: {
    coreCompletedCount: 12,
    practice: { itemsSelectedByCondition: {}, bktOnCount: 20, bktOffCount: 20, sessionsCreated: 5 },
    retention: { enrolledByCondition: {}, reviewsDelivered: 18, averageDelayDays: 1.5 },
    probes: { assigned: 10, completed: 8, completionRate: 0.8 },
    policyViolations: 0,
  },
};

describe("AdminResearchPage", () => {
  beforeEach(() => {
    getResearchAdminSummary.mockReset();
  });

  it("loads and renders a study's fidelity summary, including its condition letters", async () => {
    getResearchAdminSummary.mockResolvedValue(SUMMARY);

    render(<AdminResearchPage />);
    fireEvent.change(screen.getByPlaceholderText("Study id"), { target: { value: "study-1" } });
    fireEvent.click(screen.getByRole("button", { name: /Load study/i }));

    await screen.findByText("BKT x SM-2 Study");
    expect(getResearchAdminSummary).toHaveBeenCalledWith("study-1");
    expect(screen.getByText("ACTIVE")).toBeInTheDocument();
    expect(screen.getByText("58 / 60")).toBeInTheDocument();
    expect(screen.getByText("C")).toBeInTheDocument();
    expect(screen.getByText("BS")).toBeInTheDocument();
  });

  it("shows the backend's error message when the study fails to load", async () => {
    getResearchAdminSummary.mockRejectedValue(new Error("No such study"));

    render(<AdminResearchPage />);
    fireEvent.change(screen.getByPlaceholderText("Study id"), { target: { value: "bad-id" } });
    fireEvent.click(screen.getByRole("button", { name: /Load study/i }));

    await screen.findByText("No such study");
  });
});
