import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import AdminApp from "./AdminApp";
import ManagementShell from "./components/management/ManagementShell";

vi.mock("./pages/TeacherPracticeDebugPage", () => ({
  default: () => <p>Practice debug content</p>,
}));

describe("admin-only diagnostic navigation", () => {
  beforeEach(() => {
    localStorage.setItem("adminConsoleSession", "true");
  });

  it("opens Practice Debug from the admin navigation", async () => {
    const user = userEvent.setup();
    render(<AdminApp />);

    await user.click(screen.getByRole("button", { name: "Practice Debug" }));
    expect(screen.getByText("Practice debug content")).toBeInTheDocument();

    expect(screen.queryByRole("button", { name: "Benchmark" })).not.toBeInTheDocument();
  });

  it("does not render diagnostic entries in the teacher navigation", () => {
    render(
      <ManagementShell
        role="teacher"
        activeView="overview"
        onSelectView={() => undefined}
        submissionCount={0}
        openHelpCount={0}
        onLogout={() => undefined}
      >
        <p>Teacher content</p>
      </ManagementShell>,
    );

    expect(screen.queryByRole("button", { name: "Practice Debug" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Benchmark" })).not.toBeInTheDocument();
  });
});
