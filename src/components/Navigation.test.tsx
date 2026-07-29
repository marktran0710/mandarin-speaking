import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Navigation from "./Navigation";

/** The navbar is the only directed edge into most student pages, so a page
 * with a render branch but no link here is unreachable (that is how
 * image-narration and listen-retell went dead). These tests pin the edges. */
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
  it("always links the three core student sections", async () => {
    const user = userEvent.setup();
    const onNavigate = renderStudentNav();

    await user.click(screen.getByRole("button", { name: /Practice/ }));
    expect(onNavigate).toHaveBeenCalledWith("student-practice");

    await user.click(screen.getByRole("button", { name: /Tone practice/ }));
    expect(onNavigate).toHaveBeenCalledWith("tone-practice");

    await user.click(screen.getByRole("button", { name: /My Profile/ }));
    expect(onNavigate).toHaveBeenCalledWith("student-stories");
  });

  it("links picture-talk once the class has a describe story", async () => {
    const user = userEvent.setup();
    const onNavigate = renderStudentNav({ hasDescribeStories: true });

    await user.click(screen.getByRole("button", { name: /Picture talk/ }));
    expect(onNavigate).toHaveBeenCalledWith("image-narration");
  });

  it("links listen-and-retell once the class has a listen_retell story", async () => {
    const user = userEvent.setup();
    const onNavigate = renderStudentNav({ hasListenRetellStories: true });

    await user.click(screen.getByRole("button", { name: /Listen & retell/ }));
    expect(onNavigate).toHaveBeenCalledWith("listen-retell");
  });

  it("hides both extra sections when no story of that mode is published", () => {
    renderStudentNav();

    expect(screen.queryByRole("button", { name: /Picture talk/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Listen & retell/ })).not.toBeInTheDocument();
  });

  it("hides every section tab in compact (mid-practice) mode", () => {
    renderStudentNav({
      compact: true,
      hasDescribeStories: true,
      hasListenRetellStories: true,
    });

    expect(screen.queryByRole("button", { name: /Practice/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Picture talk/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Listen & retell/ })).not.toBeInTheDocument();
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
    expect(screen.getByRole("button", { name: /Student Login/i })).toBeInTheDocument();
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
