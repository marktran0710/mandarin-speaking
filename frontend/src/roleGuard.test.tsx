import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
 * Vite entries on ONE origin sharing ONE localStorage. These cover the rule
 * that separation rests on: a session for the other role gets a block screen
 * instead of the app, and the only way through is an explicit sign-out. */
describe("role separation between the student and teacher apps", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("blocks the student site when a teacher is signed in", () => {
    signIn("teacher", "Hau");

    render(<App />);

    expect(screen.getByText(/signed in as a teacher/i)).toBeInTheDocument();
    // ...and the student site's own chrome never renders behind it.
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });

  it("blocks the teacher site when a student is signed in", () => {
    signIn("student", "Minh", "stu-7");

    render(<TeacherApp />);

    expect(screen.getByText(/signed in as a student/i)).toBeInTheDocument();
    expect(screen.queryByText("Teacher dashboard")).not.toBeInTheDocument();
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

  it("clears the session when the block's sign-out is used", async () => {
    signIn("student", "Minh", "stu-7");
    // The block reloads to land on this app's own login screen; jsdom has no
    // navigation, so assert on the state the reload would pick up.
    const reload = vi.fn();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...window.location, reload },
    });

    render(<TeacherApp />);
    await userEvent.setup().click(screen.getByRole("button", { name: /Sign out/i }));

    expect(readSession()).toBeNull();
    expect(reload).toHaveBeenCalled();
  });

  it("offers no link from the block screen to the other app", () => {
    // A one-click hop between modes is exactly what this screen prevents;
    // sign-out must be the only way forward.
    signIn("student", "Minh");

    render(<TeacherApp />);

    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
