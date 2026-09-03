import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StorySummarySection from "./StorySummarySection";

vi.mock("chart.js/auto", () => ({
  default: class MockChart {
    static register() {}
    destroy() {}
  },
}));

const scene = {
  sceneIndex: 0,
  imageUrl: "https://example.com/scene.jpg",
  transcription: "我在市場幫助朋友。",
  vocabUsed: ["市場", "幫助", "朋友"],
  vocabMissing: [],
  vocabScore: 100,
  toneAccuracy: 88,
  pronScore: 86,
  fluencyScore: 84,
  audioUrl: "/uploads/audio/scene.wav",
};

const journeyStop = {
  key: 0,
  img: scene.imageUrl,
  idx: 0,
  status: "done" as const,
  thumbnail: scene.imageUrl,
  label: "Scene 1",
};

describe("StorySummarySection student submission flow", () => {
  beforeAll(() => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
      {} as CanvasRenderingContext2D,
    );
  });

  afterAll(() => {
    vi.restoreAllMocks();
  });

  it("keeps submission disabled until every practice scene passes", () => {
    render(
      <StorySummarySection
        journeyStopsBase={[journeyStop]}
        storySubmitted={false}
        storyFeedbackResult={null}
        sceneRecordings={{}}
        submitError={null}
        allScenesRecorded={false}
        completedSceneCount={0}
        totalScenes={1}
        practiceSceneIndices={[0]}
        onSubmitStory={vi.fn()}
        onJourneyStopClick={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("button", { name: /Submit Story to Teacher/i }),
    ).toBeDisabled();
    expect(screen.getByText("0 of 1 scenes recorded")).toBeInTheDocument();
  });

  it("submits a ready story and shows the returned whole-story feedback", async () => {
    const user = userEvent.setup();
    const onSubmitStory = vi.fn();
    const { rerender } = render(
      <StorySummarySection
        journeyStopsBase={[journeyStop]}
        storySubmitted={false}
        storyFeedbackResult={null}
        sceneRecordings={{ 0: scene }}
        submitError={null}
        allScenesRecorded
        completedSceneCount={1}
        totalScenes={1}
        practiceSceneIndices={[0]}
        onSubmitStory={onSubmitStory}
        onJourneyStopClick={vi.fn()}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: /Submit Story to Teacher/i }),
    );
    expect(onSubmitStory).toHaveBeenCalledTimes(1);

    rerender(
      <StorySummarySection
        journeyStopsBase={[journeyStop]}
        storySubmitted
        storyFeedbackResult={{
          concatenatedAudioUrl: "/uploads/story_audio/complete.wav",
          storyFeedback: {
            provider: "test-ai",
            tone: { score: 88, feedback: "Tones are clear." },
            word_stress: { score: 82, feedback: "Stress is natural." },
            rhythm_pace: { score: 84, feedback: "Pace is steady." },
            pausing: { score: 86, feedback: "Pauses fit the phrases." },
          },
        }}
        sceneRecordings={{ 0: scene }}
        submitError={null}
        allScenesRecorded
        completedSceneCount={1}
        totalScenes={1}
        practiceSceneIndices={[0]}
        onSubmitStory={onSubmitStory}
        onJourneyStopClick={vi.fn()}
      />,
    );

    expect(screen.getByText(/Story submitted!/i)).toBeInTheDocument();
    expect(screen.getByText("Whole-story review")).toBeInTheDocument();
    expect(screen.getByText("Tones are clear.")).toBeInTheDocument();
    expect(document.querySelector("audio")).toHaveAttribute(
      "src",
      "http://localhost:3000/uploads/story_audio/complete.wav",
    );
  });
});
