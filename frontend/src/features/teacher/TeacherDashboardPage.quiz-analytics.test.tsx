import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TeacherDashboardPage from "./TeacherDashboardPage";
import * as db from "../../services/database";
import type { VocabQuizAttempt } from "../../services/database";

vi.mock("../../components/pitch/PitchChart", () => ({
  default: () => <div data-testid="pitch-chart">Pitch chart</div>,
}));

describe("Quiz analytics on the Students view", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => [] })));
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  const attempts: VocabQuizAttempt[] = [
    {
      id: "a1",
      storyId: "story-1",
      studentName: "Amy",
      completedAt: "2026-07-01T00:00:00Z",
      totalQuestions: 5,
      correctCount: 3,
      totalTimeMs: 25000,
      questionResults: [
        { word: "姐姐", correct: false, timeMs: 6000 },
        { word: "姐姐", correct: false, timeMs: 5000 },
        { word: "水", correct: true, timeMs: 4000 },
        { word: "水", correct: true, timeMs: 4000 },
        { word: "貓", correct: true, timeMs: 6000 },
      ],
    },
  ];

  async function openQuizAnalytics(user: ReturnType<typeof userEvent.setup>) {
    await user.click(screen.getByRole("button", { name: /Students/ }));
  }

  it("shows class-wide quiz attempts and accuracy", async () => {
    vi.spyOn(db, "canUseDatabase").mockReturnValue(true);
    vi.spyOn(db, "listVocabQuizAttempts").mockResolvedValue(attempts);

    const user = userEvent.setup();
    render(
      <TeacherDashboardPage
        records={[]}
        onDeleteRecord={vi.fn()}
        helpRequests={[]}
        onLogout={vi.fn()}
      />,
    );

    await openQuizAnalytics(user);

    // Per-student accuracy and missed words live on the roster table and the
    // student profile now; this panel keeps only the class-wide totals.
    const overview = await screen.findByRole("region", { name: "Quiz analytics overview" });
    expect(within(overview).getByText("1")).toBeInTheDocument();
    expect(within(overview).getByText("60%")).toBeInTheDocument();
  });

  it("shows an empty state when there are no quiz attempts yet", async () => {
    vi.spyOn(db, "canUseDatabase").mockReturnValue(true);
    vi.spyOn(db, "listVocabQuizAttempts").mockResolvedValue([]);

    const user = userEvent.setup();
    render(
      <TeacherDashboardPage
        records={[]}
        onDeleteRecord={vi.fn()}
        helpRequests={[]}
        onLogout={vi.fn()}
      />,
    );

    await openQuizAnalytics(user);

    expect(await screen.findByText("No quiz attempts yet")).toBeInTheDocument();
  });

  it("filters quiz analytics by the selected student", async () => {
    const twoStudentAttempts: VocabQuizAttempt[] = [
      ...attempts,
      {
        id: "a2",
        storyId: "story-1",
        studentName: "Bo",
        mode: "strikes",
        completedAt: "2026-07-02T00:00:00Z",
        totalQuestions: 2,
        correctCount: 2,
        totalTimeMs: 8000,
        questionResults: [
          { word: "水", correct: true, timeMs: 4000 },
          { word: "貓", correct: true, timeMs: 4000 },
        ],
      },
    ];
    vi.spyOn(db, "canUseDatabase").mockReturnValue(true);
    vi.spyOn(db, "listVocabQuizAttempts").mockResolvedValue(twoStudentAttempts);

    const user = userEvent.setup();
    render(
      <TeacherDashboardPage
        records={[]}
        onDeleteRecord={vi.fn()}
        helpRequests={[]}
        onLogout={vi.fn()}
      />,
    );

    await openQuizAnalytics(user);
    const overview = await screen.findByRole("region", { name: "Quiz analytics overview" });

    // Unfiltered: both attempts counted.
    expect(within(overview).getByText("2")).toBeInTheDocument();

    // Bo answered everything correctly; Amy got 3/5 — filtering to Bo should
    // move the overview to his numbers alone.
    await user.selectOptions(screen.getByLabelText("Student"), "Bo");
    expect(within(overview).getByText("1")).toBeInTheDocument();
    expect(within(overview).getByText("100%")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Student"), "all");
    expect(within(overview).getByText("2")).toBeInTheDocument();
  });
});

