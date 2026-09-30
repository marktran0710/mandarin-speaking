import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { Student } from "../../../services/api/roster-help";
import type { VocabQuizAttempt } from "../../../services/api/quiz-analytics";
import { listCustomStories } from "../../../services/api/stories-submissions";
import RoundScoresPanel from "./RoundScoresPanel";

vi.mock("../../../services/api/stories-submissions", () => ({ listCustomStories: vi.fn() }));
vi.mock("./RoundScoresChart", () => ({
  default: ({ rows }: { rows: Array<{ studentId: string }> }) => (
    <div data-testid="round-score-chart">{rows.map((row) => row.studentId).join(",")}</div>
  ),
}));

vi.mock("./StudentRoundChart", () => ({
  default: ({ studentName, lesson }: { studentName: string; lesson: { title: string } }) => (
    <div data-testid="student-round-chart">{studentName} · {lesson.title}</div>
  ),
}));

const mockListCustomStories = vi.mocked(listCustomStories);

const students: Student[] = [
  { id: "s1", name: "An", status: "active", createdAt: "2026-01-01" },
  { id: "s2", name: "Binh", status: "active", createdAt: "2026-01-02" },
  { id: "s3", name: "Chi", status: "inactive", createdAt: "2026-01-03" },
];

function attempt(overrides: Partial<VocabQuizAttempt> = {}): VocabQuizAttempt {
  return {
    id: "a1",
    storyId: "lesson-new",
    studentId: "s1",
    studentName: "An",
    mode: "tier1",
    completedAt: "2026-09-20T08:00:00Z",
    totalQuestions: 4,
    correctCount: 3,
    totalTimeMs: 1000,
    questionResults: [],
    ...overrides,
  };
}

const attempts: VocabQuizAttempt[] = [
  attempt({ id: "old-lesson", storyId: "lesson-old", completedAt: "2026-09-01T08:00:00Z" }),
  attempt({ id: "s1-r1", mode: "tier1", correctCount: 3 }),
  attempt({ id: "s1-r2", mode: "tier2", correctCount: 2, completedAt: "2026-09-21T08:00:00Z" }),
  attempt({ id: "s1-r3", mode: "tier3", correctCount: 4, completedAt: "2026-09-22T08:00:00Z" }),
  attempt({ id: "s2-r1", studentId: "s2", studentName: "Binh", mode: "tier1", correctCount: 0 }),
  attempt({ id: "s3-r1", studentId: "s3", studentName: "Chi", mode: "tier1", correctCount: 4 }),
  attempt({ id: "legacy", studentId: undefined, studentName: "An", mode: "tier3", correctCount: 4 }),
];

describe("RoundScoresPanel", () => {
  beforeEach(() => {
    mockListCustomStories.mockResolvedValue([
      { id: "lesson-old", title: "Greetings", frames: [] },
      { id: "lesson-new", title: "At the market", frames: [] },
    ]);
  });

  it("defaults to the most recent lesson and calculates KPIs from completed active-student rounds", async () => {
    render(<RoundScoresPanel students={students} attempts={attempts} />);

    const lessonSelect = await screen.findByRole("combobox", { name: "Lesson" });
    await waitFor(() => expect(lessonSelect).toHaveValue("lesson-new"));
    expect(screen.getByRole("option", { name: "At the market (lesson-new)" })).toBeInTheDocument();

    const summary = screen.getByLabelText("Filtered round score summary");
    expect(within(summary).getByText("38%")).toBeInTheDocument();
    expect(within(summary).getByText("50%")).toBeInTheDocument();
    expect(within(summary).getByText("100%")).toBeInTheDocument();
    expect(within(summary).getByText("of 2 filtered students")).toBeInTheDocument();

    const table = screen.getByRole("table");
    expect(within(table).getByText("An")).toBeInTheDocument();
    expect(within(table).getByText("Binh")).toBeInTheDocument();
    expect(within(table).queryByText("Chi")).not.toBeInTheDocument();
    expect(within(table).getByText("0%")).toBeInTheDocument();
    expect(within(table).getAllByText("Not completed")).toHaveLength(2);
    expect(within(table).getByRole("columnheader", { name: "Avg response time" })).toBeInTheDocument();
    expect(within(table).getAllByText("0.3s/question").length).toBeGreaterThan(0);
  });

  it("applies account, search, and completion filters to both chart and table", async () => {
    const user = userEvent.setup();
    render(<RoundScoresPanel students={students} attempts={attempts} />);
    await waitFor(() => expect(screen.getByRole("combobox", { name: "Lesson" })).toHaveValue("lesson-new"));

    await user.selectOptions(screen.getByRole("combobox", { name: "Student status" }), "all");
    expect(screen.getByRole("cell", { name: "inactive" })).toBeInTheDocument();
    expect(screen.getByTestId("round-score-chart")).toHaveTextContent("s1,s2,s3");

    await user.type(screen.getByRole("searchbox", { name: "Search students" }), "s3");
    expect(screen.getByRole("rowheader", { name: /Chi/ })).toBeInTheDocument();
    expect(screen.queryByRole("rowheader", { name: /An/ })).not.toBeInTheDocument();
    expect(screen.getByTestId("round-score-chart")).toHaveTextContent("s3");

    await user.clear(screen.getByRole("searchbox", { name: "Search students" }));
    await user.selectOptions(screen.getByRole("combobox", { name: "Round progress" }), "completed");
    expect(screen.getByRole("rowheader", { name: /An/ })).toBeInTheDocument();
    expect(screen.queryByRole("rowheader", { name: /Binh/ })).not.toBeInTheDocument();
  });

  it("paginates the chart and table together at 15 students", async () => {
    const user = userEvent.setup();
    const manyStudents = Array.from({ length: 16 }, (_, index): Student => ({
      id: `student-${String(index + 1).padStart(2, "0")}`,
      name: `Student ${String(index + 1).padStart(2, "0")}`,
      status: "active",
      createdAt: "2026-01-01",
    }));
    mockListCustomStories.mockResolvedValue([{ id: "lesson-empty", title: "Empty lesson", frames: [] }]);
    render(<RoundScoresPanel students={manyStudents} attempts={[]} />);
    await waitFor(() => expect(screen.getByRole("combobox", { name: "Lesson" })).toHaveValue("lesson-empty"));

    expect(screen.getByRole("rowheader", { name: /Student 01/ })).toBeInTheDocument();
    expect(screen.queryByRole("rowheader", { name: /Student 16/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByRole("rowheader", { name: /Student 16/ })).toBeInTheDocument();
    expect(screen.queryByRole("rowheader", { name: /Student 01/ })).not.toBeInTheDocument();
  });

  it("opens a per-student dashboard on the lesson selected in the class view", async () => {
    const user = userEvent.setup();
    render(<RoundScoresPanel students={students} attempts={attempts} />);
    await waitFor(() => expect(screen.getByRole("combobox", { name: "Lesson" })).toHaveValue("lesson-new"));

    await user.click(screen.getByRole("button", { name: "An" }));

    expect(screen.getByRole("heading", { level: 2, name: "An" })).toBeInTheDocument();
    expect(screen.getByText("Student dashboard")).toBeInTheDocument();
    expect(screen.getByTestId("student-round-chart")).toHaveTextContent("An · At the market");
    expect(screen.queryByRole("combobox", { name: "Lesson" })).not.toBeInTheDocument();
    expect(screen.queryByTestId("round-score-chart")).not.toBeInTheDocument();
    const lessonTable = screen.getByRole("table", { name: "Round scores by lesson for An" });
    expect(within(lessonTable).getByRole("button", { name: /At the market/ })).toBeInTheDocument();
    expect(within(lessonTable).getByRole("button", { name: /Greetings/ })).toBeInTheDocument();
  });

  it("returns to the class view with filters intact and focus on the student who was opened", async () => {
    const user = userEvent.setup();
    render(<RoundScoresPanel students={students} attempts={attempts} />);
    await waitFor(() => expect(screen.getByRole("combobox", { name: "Lesson" })).toHaveValue("lesson-new"));
    await user.selectOptions(screen.getByRole("combobox", { name: "Round progress" }), "completed");

    await user.click(screen.getByRole("button", { name: "An" }));
    await user.click(screen.getByRole("button", { name: "Back to class" }));

    expect(screen.getByRole("combobox", { name: "Round progress" })).toHaveValue("completed");
    expect(screen.getByRole("combobox", { name: "Lesson" })).toHaveValue("lesson-new");
    expect(screen.queryByRole("rowheader", { name: /Binh/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "An" })).toHaveFocus();
  });

  it("shows ID fallback and a useful empty state when lesson titles or filters are unavailable", async () => {
    const user = userEvent.setup();
    mockListCustomStories.mockRejectedValue(new Error("offline"));
    render(<RoundScoresPanel students={students} attempts={attempts} />);

    await screen.findByText("Lesson names could not be loaded. Available lesson IDs are shown instead.");
    expect(screen.getByRole("option", { name: "lesson-new" })).toBeInTheDocument();
    await user.type(screen.getByRole("searchbox", { name: "Search students" }), "does-not-exist");
    expect(screen.getByText("No matching students")).toBeInTheDocument();
  });
});
