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

vi.mock("../components/pitch/PitchChart", () => ({
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

describe("Recording trends on the Submissions view", () => {
  it("summarizes the class fluency and tone trend", async () => {
    const user = userEvent.setup();
    render(
      <TeacherDashboardPage
        records={[analyzedRecord]}
        onDeleteRecord={vi.fn()}
        helpRequests={[]}
        onLogout={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: /Submissions/ }));

    await screen.findByText("Fluency & tone accuracy over time");
    // Scope to the trends summary: the recording cards on the same view
    // show their own per-recording scores.
    const summary = screen.getByRole("region", { name: "Recording analytics overview" });
    expect(within(summary).getByText("78/100")).toBeInTheDocument();
    expect(within(summary).getByText("86%")).toBeInTheDocument();
  });

  it("shows an empty state when there are no recordings yet", async () => {
    const user = userEvent.setup();
    render(
      <TeacherDashboardPage
        records={[]}
        onDeleteRecord={vi.fn()}
        helpRequests={[]}
        onLogout={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: /Submissions/ }));

    expect(await screen.findByText("No recordings yet")).toBeInTheDocument();
  });
});
