import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import AdminApp from "./AdminApp";
import ManagementShell from "../components/management/ManagementShell";
import { SESSION_EXPIRED_EVENT } from "@shared/api/client";

vi.mock("../features/teacher/TeacherPracticeDebugPage", () => ({
  default: () => <p>Practice debug content</p>,
}));
vi.mock("../features/admin/AdminAudioLibraryPage", () => ({
  default: () => <p>Audio library content</p>,
}));
vi.mock("../features/admin/AdminVocabularyPage", () => ({ default: () => <p>Speaking vocabulary content</p> }));

describe("admin-only diagnostic navigation", () => {
  beforeEach(() => {
    localStorage.setItem("adminConsoleSession", "true");
  });

  it("shows the admin overview shortcuts and keeps them connected to navigation", async () => {
    const user = userEvent.setup();
    render(<AdminApp />);

    expect(screen.getByRole("heading", { name: "Admin overview", level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Materials.*Stories and lesson content/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Research" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Materials.*Stories and lesson content/ }));
    expect(screen.getByRole("heading", { name: "Materials", level: 1 })).toBeInTheDocument();
  });

  it("opens Practice Debug from the admin navigation", async () => {
    const user = userEvent.setup();
    render(<AdminApp />);

    await user.click(screen.getByRole("button", { name: "Practice Debug" }));
    expect(screen.getByText("Practice debug content")).toBeInTheDocument();

    expect(screen.queryByRole("button", { name: "Benchmark" })).not.toBeInTheDocument();
  });

  it("opens the admin audio library from the admin navigation", async () => {
    const user = userEvent.setup();
    render(<AdminApp />);

    await user.click(screen.getByRole("button", { name: "Audio Library" }));
    expect(screen.getByText("Audio library content")).toBeInTheDocument();
  });
  it("opens vocabulary from the admin navigation", async () => {
    const user = userEvent.setup();
    render(<AdminApp />);
    await user.click(screen.getByRole("button", { name: "Content Bank" }));
    expect(screen.getByRole("heading", { name: "Content Bank", level: 1 })).toBeInTheDocument();
    expect(screen.getByText("Speaking vocabulary content")).toBeInTheDocument();
  });

  it("keeps story materials in the admin navigation", async () => {
    const user = userEvent.setup();
    render(<AdminApp />);

    await user.click(screen.getByRole("button", { name: "Materials" }));

    expect(screen.getByRole("heading", { name: "Materials", level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Story Builder/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /AI Image Builder/ })).toBeInTheDocument();
  });

  it("recovers from a stale authenticated flag when a request comes back 401", async () => {
    render(<AdminApp />);
    // Sanity check: the stale localStorage flag alone is enough to skip the
    // login screen and show the authenticated shell.
    expect(screen.getByRole("button", { name: "Log out" })).toBeInTheDocument();

    window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT, { detail: { role: "admin" } }));

    await waitFor(() => expect(screen.getByRole("button", { name: "Enter admin console" })).toBeInTheDocument());
    expect(screen.getByText(/session expired/i)).toBeInTheDocument();
    expect(localStorage.getItem("adminConsoleSession")).toBeNull();
  });

  it("ignores a session-expired event meant for a different role", async () => {
    render(<AdminApp />);
    window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT, { detail: { role: "teacher" } }));

    // No re-render should knock it back to the login screen.
    expect(screen.getByRole("button", { name: "Log out" })).toBeInTheDocument();
    expect(localStorage.getItem("adminConsoleSession")).toBe("true");
  });

  it("does not render diagnostic entries in the teacher navigation", () => {
    render(
      <ManagementShell
        role="teacher"
        activeView="today"
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
    expect(screen.queryByRole("button", { name: "Materials" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Vocabulary" })).not.toBeInTheDocument();
  });
});
