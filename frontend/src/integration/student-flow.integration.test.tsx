import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import StudentWorkspaceShell from "../components/student-workspace/StudentWorkspaceShell";
import StudentLoginPage from "../pages/StudentLoginPage";
import App from "../App";
import { currentRole, signIn, signOut } from "../utils/session";
import type { Topic } from "../components/TopicSelector";

const topic: Topic = {
  id: "integration-story",
  name: "Integration practice",
  description: "A deterministic story used by the frontend integration suite.",
  skillFocus: "Speaking",
  images: ["/integration-scene.png"],
  vocabulary: { 0: ["好"] },
  vocabularyPinyin: { 0: ["hǎo"] },
  vocabularyTranslation: { 0: ["good"] },
  suggestedAnswers: { 0: "好。" },
};

const workspaceProps = {
  view: "practice" as const,
  onViewChange: vi.fn(),
  onAddRecord: vi.fn(),
  helpRequests: [],
  onRaiseHand: vi.fn(),
  storyTopics: [topic],
  audioRecords: [],
  onSessionActiveChange: vi.fn(),
  onLogout: vi.fn(),
  isInPracticeSession: false,
};

describe("student integration flows", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
    vi.stubGlobal("fetch", vi.fn());
    window.scrollTo = vi.fn();
    signIn("student", "Integration Student", "student-integration");
  });

  it("keeps the learner workspace focused on the practice catalogue", () => {
    render(<StudentWorkspaceShell {...workspaceProps} />);

    expect(screen.getByRole("heading", { name: /選一個生活情境/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /課程/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /我的學習/ })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Ask teacher for help" })).not.toBeInTheDocument();
    expect(screen.queryByText("Start practice")).not.toBeInTheDocument();
    expect(screen.queryByText("開始練習")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Start activity/ })).not.toBeInTheDocument();
  });

  it("creates a student session from the dedicated login form", async () => {
    const user = userEvent.setup();
    const onLogin = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            id: "student-42",
            name: "Student 42",
            createdAt: "2026-08-22T00:00:00.000Z",
            status: "active",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    render(<StudentLoginPage onLogin={onLogin} />);
    await user.type(screen.getByPlaceholderText(/Enter your name/), "Student 42");
    await user.type(screen.getByPlaceholderText(/Enter your password/), "123456");
    await user.click(screen.getByRole("button", { name: /Enter Student Mode/ }));

    expect(onLogin).toHaveBeenCalledOnce();
    expect(currentRole("student")).toBe("student");
    expect(JSON.parse(localStorage.getItem("studentSession") ?? "{}")).toMatchObject({
      id: "student-42",
      name: "Student 42",
      role: "student",
    });
  });

  it("moves from the public landing page into the learner workspace", async () => {
    const user = userEvent.setup();
    signOut();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            id: "student-app-flow",
            name: "App Flow Student",
            createdAt: "2026-08-22T00:00:00.000Z",
            status: "active",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    render(<App />);
    await user.click(screen.getByRole("button", { name: /Start Learning/ }));
    await user.type(screen.getByPlaceholderText(/Enter your name/), "App Flow Student");
    await user.type(screen.getByPlaceholderText(/Enter your password/), "123456");
    await user.click(screen.getByRole("button", { name: /Enter Student Mode/ }));

    expect(await screen.findByRole("heading", { name: /選一個生活情境/ })).toBeInTheDocument();
    expect(screen.getByText("App Flow Student")).toBeInTheDocument();
  });

  it("keeps student and teacher sessions independent", () => {
    signIn("student", "Student 42", "student-42");
    signIn("teacher", "Teacher 42", "teacher-42");

    expect(currentRole("student")).toBe("student");
    expect(currentRole("teacher")).toBe("teacher");

    signOut("teacher");
    expect(currentRole("student")).toBe("student");
    expect(currentRole("teacher")).toBeNull();
  });
});
