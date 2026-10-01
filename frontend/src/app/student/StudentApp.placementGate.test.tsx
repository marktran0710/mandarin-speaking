import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import StudentApp from "./StudentApp";

const gate = vi.hoisted(() => ({
  initial: "required" as "loading" | "required" | "clear",
  afterRefresh: "clear" as "loading" | "required" | "clear",
  introSeen: false,
}));

vi.mock("../../utils/studentSession", () => ({
  getStudentId: () => "student-1",
  getStudentScopeKey: () => "student-1",
  getStudentName: () => "Student One",
  isAdminSession: () => false,
}));

vi.mock("../../features/placement/usePlacementGate", async () => {
  const react = await vi.importActual<typeof import("react")>("react");
  return {
    usePlacementGate: () => {
      const [state, setState] = react.useState(gate.initial);
      return { state, refresh: async () => setState(gate.afterRefresh) };
    },
  };
});

vi.mock("../../features/onboarding/onboardingFlag", () => ({
  hasSeenOnboarding: () => gate.introSeen,
  markOnboardingSeen: () => {
    gate.introSeen = true;
  },
}));

vi.mock("../../features/placement/PlacementPage", () => ({
  default: ({ gated, onCompleted, onStartLearning }: { gated?: boolean; onCompleted?: () => void; onStartLearning?: () => void }) => (
    <div data-testid="placement-mock" data-gated={String(Boolean(gated))}>
      <button onClick={onCompleted}>test finished</button>
      {onStartLearning && <button onClick={onStartLearning}>go learn</button>}
    </div>
  ),
}));
vi.mock("../../features/study/StudyPage", () => ({ default: () => <div data-testid="study-mock" /> }));
vi.mock("../../features/progress/ProgressPage", () => ({ default: () => <div data-testid="progress-mock" /> }));
vi.mock("../../features/settings/StudentSettingsPage", () => ({ default: () => <div data-testid="settings-mock" /> }));

const renderApp = () => render(<StudentApp studentName="Student One" topics={[]} onAddRecord={vi.fn()} onLogout={vi.fn()} />);
const nav = (name: string) => screen.getByRole("button", { name });

describe("StudentApp placement gate", () => {
  beforeEach(() => {
    gate.initial = "required";
    gate.afterRefresh = "clear";
    gate.introSeen = false;
  });

  it("shows nothing but a loading card (and locked lessons) until the server has answered", () => {
    gate.initial = "loading";
    renderApp();
    expect(screen.queryByTestId("study-mock")).not.toBeInTheDocument();
    expect(screen.queryByTestId("placement-mock")).not.toBeInTheDocument();
    expect(nav("課程")).toHaveAttribute("aria-disabled", "true");
  });

  it("greets a new account with the intro, not the lessons", () => {
    renderApp();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("歡迎來到慢慢中文");
    expect(screen.queryByTestId("study-mock")).not.toBeInTheDocument();
    expect(nav("課程")).toHaveAttribute("aria-disabled", "true");
    expect(nav("進度")).toHaveAttribute("aria-disabled", "true");
    expect(nav("入門測驗")).not.toHaveAttribute("aria-disabled");
  });

  it("goes from the intro into the placement test, still gated", async () => {
    const user = userEvent.setup();
    renderApp();
    for (let step = 0; step < 3; step += 1) await user.click(screen.getByRole("button", { name: "下一步" }));
    await user.click(screen.getByRole("button", { name: "開始入門測驗" }));

    expect(screen.getByTestId("placement-mock")).toHaveAttribute("data-gated", "true");
    expect(screen.queryByTestId("study-mock")).not.toBeInTheDocument();
  });

  it("skips the intro for a student who has already seen it", () => {
    gate.introSeen = true;
    renderApp();
    expect(screen.getByTestId("placement-mock")).toBeInTheDocument();
    expect(screen.queryByText("歡迎來到慢慢中文")).not.toBeInTheDocument();
  });

  it("will not open Lessons or Progress while gated, but Settings still works", async () => {
    gate.introSeen = true;
    const user = userEvent.setup();
    renderApp();

    await user.click(nav("課程"));
    await user.click(nav("進度"));
    expect(screen.getByTestId("placement-mock")).toBeInTheDocument();
    expect(screen.queryByTestId("study-mock")).not.toBeInTheDocument();
    expect(screen.queryByTestId("progress-mock")).not.toBeInTheDocument();

    await user.click(nav("設定"));
    expect(screen.getByTestId("settings-mock")).toBeInTheDocument();
  });

  it("unlocks everything once the test is finished, keeps the result on screen, and lets the student go on", async () => {
    gate.introSeen = true;
    const user = userEvent.setup();
    renderApp();

    await user.click(screen.getByRole("button", { name: "test finished" }));
    expect(nav("課程")).not.toHaveAttribute("aria-disabled");
    expect(screen.getByTestId("placement-mock")).toBeInTheDocument(); // the result is not yanked away

    await user.click(screen.getByRole("button", { name: "go learn" }));
    expect(screen.getByTestId("study-mock")).toBeInTheDocument();
  });

  it("does not gate an account the server has cleared", () => {
    gate.initial = "clear";
    renderApp();
    expect(screen.getByTestId("study-mock")).toBeInTheDocument();
    expect(nav("課程")).not.toHaveAttribute("aria-disabled");
  });
});
