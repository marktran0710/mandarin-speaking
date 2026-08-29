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

describe("TeacherDashboardPage", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
  });

  it("opens the quiz review tool from the Materials section", async () => {
    // TeacherQuizReviewPage shipped without a nav mount, so nothing could
    // reach it — this pins the edge that makes it reachable.
    const user = userEvent.setup();
    renderDashboard();

    await user.click(screen.getByRole("button", { name: /Materials/ }));
    await user.click(screen.getByRole("button", { name: /Quiz Review/ }));

    expect(
      await screen.findByRole("heading", { name: /Quiz Review/ }),
    ).toBeInTheDocument();
  });

  it("lists a published teacher story in the My Profile by-story overview", async () => {
    const user = userEvent.setup();
    // First, create and publish a teacher story
    const { unmount } = renderDashboard();

    await user.click(screen.getByRole("button", { name: /Materials/ }));
    await user.click(screen.getByRole("button", { name: /Story Builder/ }));
    await user.clear(screen.getByLabelText("Story title"));
    await user.type(screen.getByLabelText("Story title"), "Adventure Story");
    const imageInputs = screen.getAllByLabelText("Image URL or uploaded file");
    for (let index = 0; index < imageInputs.length; index += 1) {
      await user.type(
        imageInputs[index],
        `https://example.com/adventure-${index + 1}.jpg`,
      );
    }
    await user.click(screen.getByRole("button", { name: "Save custom story" }));
    await user.click(screen.getByRole("button", { name: "Publish" }));

    unmount();

    const publishedTopics = loadPublishedTeacherTopics();
    const publishedTopic = publishedTopics.find(
      (topic) => topic.name === "Adventure Story",
    );
    expect(publishedTopic).toBeDefined();

    // Now show the student view with the published story
    render(
      <MyStoriesPage
        records={[{
          ...analyzedRecord,
          imageUrl: "https://example.com/adventure-1.jpg",
          topicId: publishedTopic!.id,
        }]}
        publishedTopics={publishedTopics}
      />,
    );

    expect(
      // The page heading is a bilingual BiLabel — its accessible name is
  // "我的學習 … My learning", so match by substring.
  screen.getByRole("heading", { name: /My learning/ }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /By story/ }));
    expect(screen.getByText("Adventure Story")).toBeInTheDocument();
  }, 15000);
});
