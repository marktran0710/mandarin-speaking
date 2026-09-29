import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Navigation from "./Navigation";

/** Student mode now has one shell entry point; the shell owns the internal
 * practice/progress tabs. */
function renderStudentNav(props: Partial<Parameters<typeof Navigation>[0]> = {}) {
  const onNavigate = vi.fn();
  render(
    <Navigation
      currentPage="student-practice"
      activeRole="student"
      onNavigate={onNavigate}
      onLogout={vi.fn()}
      {...props}
    />,
  );
  return onNavigate;
}

describe("Navigation student links", () => {
  it("routes the logged-out entry links and exposes the current page", async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();
    const props = {
      activeRole: null,
      onNavigate,
      onLogout: vi.fn(),
    } as const;
    const { rerender } = render(<Navigation currentPage="home" {...props} />);

    const home = screen.getByRole("button", { name: /首頁/ });
    const studentLogin = screen.getByRole("button", { name: /學生登入/ });
    expect(home).toHaveAttribute("aria-current", "page");
    expect(studentLogin).not.toHaveAttribute("aria-current");

    await user.click(studentLogin);
    expect(onNavigate).toHaveBeenCalledWith("student-login");

    await user.click(screen.getByRole("button", { name: /慢慢中文/ }));
    expect(onNavigate).toHaveBeenCalledWith("home");

    rerender(<Navigation currentPage="student-login" {...props} />);
    expect(screen.getByRole("button", { name: /學生登入/ })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: /首頁/ })).not.toHaveAttribute("aria-current");
  });

  it("links the single student workspace", async () => {
    const user = userEvent.setup();
    const onNavigate = renderStudentNav();
    const learningLink = screen.getByRole("button", { name: /我的學習/ });

    expect(learningLink).toHaveAttribute("aria-current", "page");
    await user.click(learningLink);
    expect(onNavigate).toHaveBeenCalledWith("student-workspace");
  });

  it("hides every section tab in compact (mid-practice) mode", () => {
    renderStudentNav({ compact: true });

    expect(screen.queryByRole("button", { name: /我的學習/ })).not.toBeInTheDocument();
  });
});

/** The two modes are separated by having no edge between them: the student
 * navbar must never advertise the teacher site, and the teacher login screen
 * must never offer a way back. Both used to render a link here. */
describe("Navigation keeps the two modes unlinked", () => {
  it("offers no teacher entry point on the logged-out student navbar", () => {
    render(
      <Navigation
        currentPage="home"
        activeRole={null}
        onNavigate={vi.fn()}
        onLogout={vi.fn()}
      />,
    );

    // The student login link is still expected — only the teacher door is gone.
    expect(screen.getByRole("button", { name: /學生登入/ })).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.queryByText(/teacher/i)).not.toBeInTheDocument();
  });

  it("offers no way back to the student site from the teacher login screen", () => {
    render(
      <Navigation
        currentPage="teacher-login"
        activeRole={null}
        onNavigate={vi.fn()}
        onLogout={vi.fn()}
        appVariant="teacher"
      />,
    );

    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.queryByText(/Back to student site/i)).not.toBeInTheDocument();
  });
});

describe("Navigation teacher variant", () => {
  it("sends the logo click somewhere real on the teacher login screen", async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();
    render(
      <Navigation
        currentPage="teacher-login"
        activeRole={null}
        onNavigate={onNavigate}
        onLogout={vi.fn()}
        appVariant="teacher"
      />,
    );

    await user.click(screen.getByRole("button", { name: /慢慢中文/ }));
    expect(onNavigate).toHaveBeenCalledWith("teacher-login");
  });
});
