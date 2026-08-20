import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import App from "./App";
import TeacherApp from "./TeacherApp";
import { readSession, signIn } from "./utils/session";

// The student app pulls in the whole practice stack; none of it matters to
// the guard, which decides before any of it renders.
vi.mock("./pages/CreateStoryPage", () => ({ default: () => <div /> }));
vi.mock("./pages/MyStoriesPage", () => ({ default: () => <div /> }));
vi.mock("./pages/TeacherDashboardPage", () => ({
  default: () => <div>Teacher dashboard</div>,
}));

/** The student site (index.html) and the teacher site (teacher.html) are two
 * Vite entries on ONE origin sharing ONE localStorage. Both role sessions may
 * exist at once; each app reads only the session for its own role. */
describe("independent role sessions between the student and teacher apps", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("lets the student site open when only a teacher is signed in", () => {
    signIn("teacher", "Hau");

    render(<App />);

    expect(screen.queryByText(/signed in as a teacher/i)).not.toBeInTheDocument();
    expect(screen.getByRole("navigation")).toBeInTheDocument();
  });

  it("lets the teacher site open when only a student is signed in", () => {
    signIn("student", "Minh", "stu-7");

    render(<TeacherApp />);

    expect(screen.queryByText(/signed in as a student/i)).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Teacher Login/ })).toBeInTheDocument();
  });

  it("lets each app through for its own role", () => {
    signIn("teacher", "Hau");
    const teacherView = render(<TeacherApp />);
    expect(screen.getByText("Teacher dashboard")).toBeInTheDocument();
    teacherView.unmount();

    localStorage.clear();
    signIn("student", "Minh");
    render(<App />);
    expect(screen.queryByText(/signed in as a/i)).not.toBeInTheDocument();
  });

  it("keeps both apps available and preserves both sessions", () => {
    signIn("student", "Minh");
    signIn("teacher", "Hau");

    const teacherView = render(<TeacherApp />);
    expect(screen.getByText("Teacher dashboard")).toBeInTheDocument();
    teacherView.unmount();

    render(<App />);
    expect(readSession("student")?.name).toBe("Minh");
    expect(readSession("teacher")?.name).toBe("Hau");
  });
});
