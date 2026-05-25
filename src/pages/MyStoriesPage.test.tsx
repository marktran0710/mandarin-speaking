import { render, screen, within } from "@testing-library/react";
import MyStoriesPage from "./MyStoriesPage";

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

vi.mock("../PitchChart", () => ({
  default: () => <div data-testid="pitch-chart">Pitch chart</div>,
}));

describe("MyStoriesPage", () => {
  it("summarizes analyzed student recordings for teachers", () => {
    render(
      <MyStoriesPage
        mode="teacher"
        records={[analyzedRecord]}
        onDeleteRecord={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "Class Speaking Dashboard" }),
    ).toBeInTheDocument();
    const overview = screen.getByRole("region", { name: "Class overview" });
    expect(within(overview).getAllByText("1")).toHaveLength(2);
    expect(within(overview).getByText("78/100")).toBeInTheDocument();
    expect(within(overview).getByText("86%")).toBeInTheDocument();
    expect(screen.getByText("Good pacing with a clear story sequence.")).toBeInTheDocument();
    expect(screen.getByTestId("pitch-chart")).toBeInTheDocument();
  });

  it("shows completed picture status in the student workbook", () => {
    render(
      <MyStoriesPage
        mode="student"
        records={[analyzedRecord]}
        onDeleteRecord={vi.fn()}
        onPracticeImage={vi.fn()}
      />,
    );

    expect(screen.getByRole("heading", { name: "My Story Workbook" })).toBeInTheDocument();
    expect(screen.getByText("1/24")).toBeInTheDocument();
    expect(screen.getByText("Feedback ready")).toBeInTheDocument();

    const firstPrompt = screen.getAllByRole("article")[0];
    expect(within(firstPrompt).getByText("Record another attempt")).toBeInTheDocument();
  });
});
