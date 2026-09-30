import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { Student } from "../../../services/api/roster-help";
import type { VocabQuizAttempt } from "../../../services/api/quiz-analytics";
import { buildStudentRoundDashboard, selectLatestRoundAttempts } from "./model";
import StudentRoundDashboard from "./StudentRoundDashboard";

vi.mock("./StudentRoundChart", () => ({
  default: ({ studentName, lesson }: { studentName: string; lesson: { title: string } }) => (
    <div data-testid="student-round-chart">{studentName} · {lesson.title}</div>
  ),
}));

const students: Student[] = [
  { id: "s1", name: "An", status: "active", createdAt: "2026-01-01" },
  { id: "s2", name: "Binh", status: "active", createdAt: "2026-01-02" },
];
const stories = [
  { id: "lesson-1", title: "Greetings" },
  { id: "lesson-2", title: "Family" },
];

function attempt(overrides: Partial<VocabQuizAttempt> = {}): VocabQuizAttempt {
  return {
    id: "a1",
    storyId: "lesson-1",
    studentId: "s1",
    studentName: "An",
    mode: "tier1",
    completedAt: "2026-09-01T08:00:00Z",
    totalQuestions: 4,
    correctCount: 3,
    totalTimeMs: 4000,
    questionResults: [],
    ...overrides,
  };
}

const attempts = [
  attempt({ id: "l1-r1", mode: "tier1", correctCount: 4 }),
  attempt({ id: "l1-r2", mode: "tier2", correctCount: 2, completedAt: "2026-09-02T08:00:00Z" }),
  attempt({ id: "l2-r1", storyId: "lesson-2", mode: "tier1", correctCount: 3, completedAt: "2026-09-10T08:00:00Z" }),
  attempt({ id: "l2-r2", storyId: "lesson-2", mode: "tier2", correctCount: 4, completedAt: "2026-09-11T08:00:00Z" }),
  attempt({ id: "l2-r3", storyId: "lesson-2", mode: "tier3", correctCount: 1, completedAt: "2026-09-12T08:00:00Z" }),
  attempt({ id: "binh", studentId: "s2", studentName: "Binh", mode: "tier1", correctCount: 2 }),
];

function dashboardFor(studentId: string, source = attempts) {
  const latest = selectLatestRoundAttempts(students, source);
  return buildStudentRoundDashboard(students, latest, studentId, stories)!;
}

describe("StudentRoundDashboard", () => {
  it("summarizes the student and lists every attempted lesson newest first", () => {
    render(<StudentRoundDashboard dashboard={dashboardFor("s1")} initialStoryId="lesson-1" onBack={() => {}} />);

    expect(screen.getByRole("heading", { level: 2, name: "An" })).toBeInTheDocument();
    expect(screen.getByText("Student dashboard")).toBeInTheDocument();

    const summary = screen.getByLabelText("Student summary");
    expect(within(summary).getByText("Lessons attempted").parentElement).toHaveTextContent("2");
    expect(within(summary).getByText("Completed all 3 rounds").parentElement).toHaveTextContent("1of 2 lessons");
    expect(within(summary).getByText("Avg response time").parentElement).toHaveTextContent(/1s.*per question.*20 questions across 5 rounds/);
    // 08:00 UTC on Sep 12 can still be Sep 11 in far-west time zones.
    expect(within(summary).getByText("Latest quiz activity").parentElement).toHaveTextContent(/Sep 1[12], 2026/);

    const table = screen.getByRole("table", { name: "Round scores by lesson for An" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByRole("button", { name: /Family/ })).toBeInTheDocument();
    expect(within(rows[1]).getByRole("button", { name: /Greetings/ })).toBeInTheDocument();
    expect(within(rows[1]).getByText("Not completed")).toBeInTheDocument();
    expect(within(rows[0]).getByText("100%")).toBeInTheDocument();
  });

  it("charts the lesson chosen in the class view and switches when another lesson row is picked", async () => {
    const user = userEvent.setup();
    render(<StudentRoundDashboard dashboard={dashboardFor("s1")} initialStoryId="lesson-1" onBack={() => {}} />);

    expect(screen.getByTestId("student-round-chart")).toHaveTextContent("An · Greetings");
    expect(screen.getByRole("button", { name: /Greetings/ })).toHaveAttribute("aria-pressed", "true");

    await user.click(screen.getByRole("button", { name: /Family/ }));
    expect(screen.getByTestId("student-round-chart")).toHaveTextContent("An · Family");
    expect(screen.getByRole("button", { name: /Family/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /Greetings/ })).toHaveAttribute("aria-pressed", "false");
  });

  it("falls back to the newest lesson when the class-view lesson was never attempted by this student", () => {
    render(<StudentRoundDashboard dashboard={dashboardFor("s2")} initialStoryId="lesson-2" onBack={() => {}} />);

    expect(screen.getByTestId("student-round-chart")).toHaveTextContent("Binh · Greetings");
  });

  it("moves focus to the heading on open and calls onBack from the back button", async () => {
    const user = userEvent.setup();
    const onBack = vi.fn();
    render(<StudentRoundDashboard dashboard={dashboardFor("s1")} initialStoryId="lesson-1" onBack={onBack} />);

    expect(screen.getByRole("heading", { level: 2, name: "An" })).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Back to class" }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it("shows an empty state instead of a chart when the student has no completed rounds", () => {
    render(<StudentRoundDashboard dashboard={dashboardFor("s1", [])} initialStoryId="" onBack={() => {}} />);

    expect(screen.getByText("No completed rounds yet")).toBeInTheDocument();
    expect(screen.queryByTestId("student-round-chart")).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
