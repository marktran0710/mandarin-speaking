import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TopicSelector from "../components/TopicSelector";
import TeacherDashboardPage from "./TeacherDashboardPage";
import MyStoriesPage, { type AudioRecord } from "./MyStoriesPage";
import * as db from "../services/database";
import type { VocabQuizAttempt } from "../services/database";
import { loadPublishedTeacherTopics } from "../utils/teacherStories";

const analyzedRecord = {
  id: "record-1",
  timestamp: "5/25/2026, 10:00 AM",
  duration: 42,
  transcription: "我和朋友去森林冒險，最後找到了地圖。",
  model: "gemini",
  topicId: "adventure",
  imageUrl: "https://picsum.photos/400/300?random=1",
  imageIndex: 0,
  praatMetrics: {
    pitch_contour: [
      [0, 180],
      [0.2, 195],
      [0.4, 188],
    ],
    word_prosody: [
      {
        token: "冒",
        index: 0,
        pitch_contour: [
          [0, 180],
          [0.2, 195],
        ],
        tone_accuracy: 86,
        judged: true,
        mean_pitch: 188,
        pitch_range: 15,
        contour_shape: "rising",
        feedback: "The tone is clear.",
      },
    ],
    detected_tone: 2,
    tone_accuracy: 86,
    formants: {
      F1: 500,
      F2: 1500,
      F3: 2500,
    },
    speech_rate: 3.2,
    fluency_score: 78,
    pitch_statistics: {},
    feedback: "Your pitch movement is clear.",
    ai_feedback: {
      provider: "gemini",
      fluency: {
        score: 82,
        feedback: "Good pacing with a clear story sequence.",
      },
      grammar: {
        score: 76,
        feedback: "Use more complete connectors between events.",
        corrections: ["Add 然後 before the second event."],
      },
      vocabulary: {
        score: 80,
        feedback: "Good topic words. Add one feeling word.",
        suggestions: ["興奮", "緊張"],
      },
      improved_version: "我和朋友去森林冒險，然後找到了地圖。",
      practice_prompt: "Try adding one sentence about how you felt.",
    },
  },
};

vi.mock("../components/PitchChart", () => ({
  default: () => <div data-testid="pitch-chart">Pitch chart</div>,
}));

function renderDashboard(records: AudioRecord[] = []) {
  return render(
    <TeacherDashboardPage
      records={records}
      onDeleteRecord={vi.fn()}
      helpRequests={[]}
      onLogout={vi.fn()}
    />,
  );
}

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

  it("shows per-student accuracy, time, and repeated-mistake analytics", async () => {
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

    // Per-student accuracy lives on the roster table now; this panel keeps
    // the class-wide numbers and the repeated-mistake list.
    const overview = await screen.findByRole("region", { name: "Quiz analytics overview" });
    expect(within(overview).getByText("60%")).toBeInTheDocument();

    const wordHeading = screen.getByRole("heading", { name: "Words Needing the Most Practice" });
    const wordPanel = wordHeading.closest(".teacher-quiz-analytics-panel") as HTMLElement;
    expect(within(wordPanel).getByText("姐姐")).toBeInTheDocument();
    expect(within(wordPanel).getByText(/Missed 2\/2 times \(100%\)/)).toBeInTheDocument();
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
    const wordPanel = screen
      .getByRole("heading", { name: "Words Needing the Most Practice" })
      .closest(".teacher-quiz-analytics-panel") as HTMLElement;

    // Unfiltered: both attempts counted, and Amy's repeated miss is listed.
    expect(within(overview).getByText("2")).toBeInTheDocument();
    expect(within(wordPanel).getByText("姐姐")).toBeInTheDocument();

    // Bo answered everything correctly, so filtering to Bo empties both.
    await user.selectOptions(screen.getByLabelText("Student"), "Bo");
    expect(within(overview).getByText("1")).toBeInTheDocument();
    expect(within(wordPanel).queryByText("姐姐")).not.toBeInTheDocument();
    expect(within(wordPanel).getByText("No repeated mistakes yet")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Student"), "all");
    expect(within(overview).getByText("2")).toBeInTheDocument();
    expect(within(wordPanel).getByText("姐姐")).toBeInTheDocument();
  });
});

