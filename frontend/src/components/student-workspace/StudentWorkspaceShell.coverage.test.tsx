import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import StudentWorkspaceShell from "./StudentWorkspaceShell";

vi.mock("../../pages/CreateStoryPage", () => ({
  default: ({ onPanelScrollBoundary }: { onPanelScrollBoundary: () => void }) => (
    <section>
      <span>practice view</span>
      <button type="button" onClick={onPanelScrollBoundary}>Trigger boundary</button>
    </section>
  ),
}));

vi.mock("../../pages/MyStoriesPage", () => ({
  default: ({ onBrowsePractice }: { onBrowsePractice: () => void }) => (
    <section>
      <span>progress view</span>
      <button type="button" onClick={onBrowsePractice}>Browse practice</button>
    </section>
  ),
}));

vi.mock("./StudentModeFrame", () => ({
  STUDENT_WORKSPACE_VIEWS: [
    { id: "practice", label: { zh: "課程", en: "Practice" } },
    { id: "progress", label: { zh: "我的學習", en: "Progress" } },
  ],
  default: ({ children, onChange }: { children: React.ReactNode; onChange: (view: "practice" | "progress") => void }) => (
    <main>
      <button type="button" onClick={() => onChange("practice")}>Choose practice</button>
      <button type="button" onClick={() => onChange("progress")}>Choose progress</button>
      {children}
    </main>
  ),
}));

vi.mock("../../utils/quizTiers", () => ({
  loadBestLocalStars: vi.fn(() => 2),
}));

vi.mock("../../utils/topicQuiz", () => ({
  topicHasQuiz: vi.fn(() => true),
}));

vi.mock("../../utils/myStoriesUtils", () => ({
  getAverageMetric: vi.fn(() => 82),
}));

vi.mock("../../utils/studentSession", () => ({
  getStudentName: vi.fn(() => "Integration Student"),
}));

const props = {
  view: "practice" as const,
  onViewChange: vi.fn(),
  onAddRecord: vi.fn(),
  initialTopicId: undefined,
  initialImageIndex: undefined,
  initialStartAtQuiz: false,
  initialTargetKey: undefined,
  helpRequests: [],
  onRaiseHand: vi.fn(),
  storyTopics: [],
  audioRecords: [],
  onSessionActiveChange: vi.fn(),
  onLogout: vi.fn(),
  isInPracticeSession: false,
};

describe("StudentWorkspaceShell coverage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders practice, handles a boundary event, and ignores selecting the active view", async () => {
    const user = userEvent.setup();
    render(<StudentWorkspaceShell {...props} />);

    await user.click(screen.getByRole("button", { name: "Trigger boundary" }));
    await user.click(screen.getByRole("button", { name: "Choose practice" }));
    expect(props.onViewChange).not.toHaveBeenCalled();
  });

  it("renders progress and routes the browse action back to practice", async () => {
    const user = userEvent.setup();
    render(<StudentWorkspaceShell {...props} view="progress" />);

    expect(screen.getByText("progress view")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Browse practice" }));
    expect(props.onViewChange).toHaveBeenCalledWith("practice");
  });

  it("covers an active story target and missing optional collections", () => {
    const { rerender } = render(
      <StudentWorkspaceShell
        {...props}
        view={"unknown" as "practice"}
        initialTopicId="story-1"
        initialImageIndex={1}
        initialStartAtQuiz
        initialTargetKey={1}
        storyTopics={undefined as never}
        audioRecords={undefined as never}
      />,
    );

    expect(screen.getByText("practice view")).toBeInTheDocument();

    rerender(
      <StudentWorkspaceShell
        {...props}
        view={"unknown" as "practice"}
        initialTopicId="story-1"
        initialImageIndex={undefined}
        initialStartAtQuiz={false}
        initialTargetKey={undefined}
        storyTopics={undefined as never}
        audioRecords={undefined as never}
      />,
    );
    expect(screen.getByText("practice view")).toBeInTheDocument();
  });
});
