import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import AdminInsightsWorkspace from "./AdminInsightsWorkspace";

vi.mock("../../components/analytics/AdminIrtStudentPanel", () => ({ default: () => <p>Student panel</p> }));
vi.mock("../../components/analytics/MeasurementAnalyticsPanel", () => ({ default: () => <p>Measurement panel</p> }));
vi.mock("../../components/analytics/KnowledgeModelPilotPanel", () => ({ default: () => <p>Knowledge panel</p> }));
vi.mock("./round-scores/RoundScoresPanel", () => ({ default: () => <p>Round score panel</p> }));

describe("AdminInsightsWorkspace tabs", () => {
  it("lazy-loads Round scores and wires tab accessibility attributes", async () => {
    const user = userEvent.setup();
    render(<AdminInsightsWorkspace students={[]} attempts={[]} records={[]} events={[]} />);

    const roundTab = screen.getByRole("tab", { name: "Round scores" });
    expect(roundTab).toHaveAttribute("aria-controls", "admin-insight-panel-round-scores");
    await user.click(roundTab);

    expect(await screen.findByText("Round score panel")).toBeInTheDocument();
    expect(roundTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveAttribute("aria-labelledby", "admin-insight-tab-round-scores");
  });

  it("supports arrow, Home, and End keyboard navigation", async () => {
    const user = userEvent.setup();
    render(<AdminInsightsWorkspace students={[]} attempts={[]} records={[]} events={[]} />);

    const studentTab = screen.getByRole("tab", { name: "Student analytics" });
    studentTab.focus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Round scores" })).toHaveFocus();
    expect(await screen.findByText("Round score panel")).toBeInTheDocument();

    await user.keyboard("{End}");
    expect(screen.getByRole("tab", { name: "Measurement health" })).toHaveFocus();
    expect(screen.getByText("Measurement panel")).toBeInTheDocument();

    await user.keyboard("{Home}");
    expect(studentTab).toHaveFocus();
    expect(screen.getByText("Student panel")).toBeInTheDocument();
  });
});
