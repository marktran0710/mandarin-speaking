import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import AdminApp from "./AdminApp";
import TeacherShell from "./components/teacher/TeacherShell";

vi.mock("./pages/TeacherPracticeDebugPage", () => ({
  default: () => <p>Practice debug content</p>,
}));
vi.mock("./pages/TeacherBenchmarkPage", () => ({
  default: () => <p>Benchmark content</p>,
}));

describe("admin-only diagnostic navigation", () => {
  beforeEach(() => {
    localStorage.setItem("adminConsoleSession", "true");
  });

  it("opens Practice Debug and Benchmark from the admin navigation", async () => {
    const user = userEvent.setup();
    render(<AdminApp />);

    await user.click(screen.getByRole("button", { name: "Practice Debug" }));
    expect(screen.getByText("Practice debug content")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Benchmark" }));
    expect(screen.getByText("Benchmark content")).toBeInTheDocument();
  });

  it("does not render diagnostic entries in the teacher navigation", () => {
    render(
      <TeacherShell
        activeView="overview"
        onSelectView={() => undefined}
        submissionCount={0}
        openHelpCount={0}
        onLogout={() => undefined}
      >
        <p>Teacher content</p>
      </TeacherShell>,
    );

    expect(screen.queryByRole("button", { name: "Practice Debug" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Benchmark" })).not.toBeInTheDocument();
  });
});
