import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import App from "./App";

vi.setConfig({ testTimeout: 15000 });

const TEST_BACKEND_URL =
  import.meta.env.VITE_BACKEND_URL || "http://127.0.0.1:8000";

describe("App role flows", () => {
  it.skip("opens the teacher dashboard after teacher login", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Teacher Login" }));
    expect(
      screen.getByRole("heading", { name: "教師登入" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Teacher name")).toHaveValue("Teacher Demo");

    await user.click(
      screen.getByRole("button", { name: "Enter Teacher Mode" }),
    );

    expect(
      screen.getByRole("heading", { name: "Class Speaking Dashboard" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Submissions")).toBeInTheDocument();
    expect(screen.getByText("No submissions yet")).toBeInTheDocument();
  });

  it.skip("lets teachers generate six image cues from a situation context", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        provider: "gemini-2.0-flash",
        title: "MRT Help Story",
        learning_goal: "Students describe a problem and ask for help.",
        frames: Array.from({ length: 6 }, (_, index) => ({
          index: index + 1,
          title: `Scene ${index + 1}`,
          student_prompt: `Describe scene ${index + 1}.`,
          vocabulary: ["MRT", "help", "thank you"],
          image_prompt: `Comic scene ${index + 1}`,
          image_url: `data:image/svg+xml,<svg></svg>#${index + 1}`,
        })),
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await user.click(screen.getByRole("button", { name: "Teacher Login" }));
    await user.click(
      screen.getByRole("button", { name: "Enter Teacher Mode" }),
    );
    await user.click(screen.getByRole("button", { name: "Image Builder" }));

    expect(
      screen.getByRole("heading", { name: "Generate Six Picture Cues" }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Generate 6 images" }));

    expect(fetchMock).toHaveBeenCalledWith(
      `${TEST_BACKEND_URL}/api/generate-story-images`,
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
      }),
    );
    expect(
      await screen.findByRole("heading", { name: "MRT Help Story" }),
    ).toBeInTheDocument();
    expect(screen.getAllByAltText(/Generated story frame/)).toHaveLength(6);

    await user.click(
      screen.getByRole("button", { name: "Save to story library" }),
    );

    expect(localStorage.getItem("teacherCustomStories")).toContain(
      "MRT Help Story",
    );
    expect(
      screen.getByText("Generated story saved to the teacher story library."),
    ).toBeInTheDocument();

    vi.unstubAllGlobals();
  });


  it.skip("lets a student raise a hand and a teacher mark the request helped", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: /Student Login/ }));
    await user.type(screen.getByLabelText(/Student name/), "Student Demo");
    await user.type(screen.getByLabelText(/Password/), "123456");
    await user.click(
      screen.getByRole("button", { name: /Enter Student Mode/ }),
    );
    await user.clear(screen.getByLabelText("Help request message"));
    await user.type(
      screen.getByLabelText("Help request message"),
      "Please help me with tones.",
    );
    await user.click(screen.getByRole("button", { name: "Raise hand" }));

    expect(
      screen.getByText("Teacher has your help request"),
    ).toBeInTheDocument();
    expect(localStorage.getItem("helpRequests")).toContain(
      "Please help me with tones.",
    );

    await user.click(screen.getByRole("button", { name: "Log out" }));
    await user.click(screen.getByRole("button", { name: "Teacher Login" }));
    await user.click(
      screen.getByRole("button", { name: "Enter Teacher Mode" }),
    );

    expect(screen.getByText("Student Help Requests")).toBeInTheDocument();
    expect(screen.getByText("Student Demo")).toBeInTheDocument();
    expect(screen.getByText("Please help me with tones.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Mark helped" }));

    expect(screen.getByText("No raised hands")).toBeInTheDocument();
    expect(localStorage.getItem("helpRequests")).toContain("resolved");
  });

  it("no longer grants teacher access from a stale localStorage flag", () => {
    // The teacher dashboard moved to a separate app (TeacherApp.tsx) gated by
    // a real backend-issued token — this app must not resurrect a teacher
    // session just because an old `activeRole=teacher` flag is still around
    // from the previous fake-login scheme.
    localStorage.setItem("activeRole", "teacher");

    render(<App />);

    expect(screen.queryByText("Class overview")).not.toBeInTheDocument();
  });
});
