import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TopicSelector from "../TopicSelector";
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
  beforeEach(() => {
    localStorage.clear();
  });

  it("summarizes analyzed student recordings for teachers", () => {
    const user = userEvent.setup();
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
    expect(screen.getByRole("navigation", { name: "Teacher tools" })).toBeInTheDocument();
    return user.click(screen.getByRole("button", { name: /Recordings/ })).then(() => {
    expect(screen.getByText("Good pacing with a clear story sequence.")).toBeInTheDocument();
    expect(screen.getByTestId("pitch-chart")).toBeInTheDocument();
    });
  });

  it("lets teachers save a custom image-based story activity", async () => {
    const user = userEvent.setup();
    render(
      <MyStoriesPage
        mode="teacher"
        records={[]}
        onDeleteRecord={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: /Materials/ }));
    await user.clear(screen.getByLabelText("Story title"));
    await user.type(screen.getByLabelText("Story title"), "Taipei Rain Rescue");
    const imageInputs = screen.getAllByLabelText("Image URL or uploaded file");
    for (let index = 0; index < imageInputs.length; index += 1) {
      await user.type(
        imageInputs[index],
        `https://example.com/rain-scene-${index + 1}.jpg`,
      );
    }
    await user.clear(screen.getAllByLabelText("Student prompt")[0]);
    await user.type(
      screen.getAllByLabelText("Student prompt")[0],
      "Describe how the student helps someone in the rain.",
    );
    await user.type(screen.getAllByLabelText("Vocabulary")[0], "下雨, 幫忙");

    await user.click(screen.getByRole("button", { name: "Save custom story" }));

    const library = screen.getByLabelText("Saved custom stories");
    expect(within(library).getByText("Taipei Rain Rescue")).toBeInTheDocument();
    expect(localStorage.getItem("teacherCustomStories")).toContain(
      "Taipei Rain Rescue",
    );
  }, 10000);

  it("lets teachers edit a saved custom story activity", async () => {
    const user = userEvent.setup();
    render(
      <MyStoriesPage
        mode="teacher"
        records={[]}
        onDeleteRecord={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: /Materials/ }));
    await user.clear(screen.getByLabelText("Story title"));
    await user.type(screen.getByLabelText("Story title"), "Original Story");
    for (const [index, input] of screen.getAllByLabelText("Image URL or uploaded file").entries()) {
      await user.type(input, `https://example.com/edit-scene-${index + 1}.jpg`);
    }
    await user.click(screen.getByRole("button", { name: "Save custom story" }));

    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.clear(screen.getByLabelText("Story title"));
    await user.type(screen.getByLabelText("Story title"), "Edited Story");
    await user.click(screen.getByRole("button", { name: "Update custom story" }));

    const stored = localStorage.getItem("teacherCustomStories") || "";
    expect(stored).toContain("Edited Story");
    expect(stored).not.toContain("Original Story");
    expect(JSON.parse(stored)).toHaveLength(1);
  }, 10000);

  it("publishes a teacher story into the student topic selector", async () => {
    const user = userEvent.setup();
    const { unmount } = render(
      <MyStoriesPage
        mode="teacher"
        records={[]}
        onDeleteRecord={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: /Materials/ }));
    await user.clear(screen.getByLabelText("Story title"));
    await user.type(screen.getByLabelText("Story title"), "Published MRT Help");
    for (const [index, input] of screen.getAllByLabelText("Image URL or uploaded file").entries()) {
      await user.type(input, `https://example.com/published-scene-${index + 1}.jpg`);
    }
    await user.click(screen.getByRole("button", { name: "Save custom story" }));
    await user.click(screen.getByRole("button", { name: "Publish" }));

    expect(localStorage.getItem("teacherCustomStories")).toContain(
      "\"published\":true",
    );

    unmount();
    render(<TopicSelector />);

    expect(screen.getByRole("button", { name: /Published MRT Help/ })).toBeInTheDocument();
  }, 10000);

  it("shows validation errors when a teacher saves an incomplete custom story", async () => {
    const user = userEvent.setup();
    render(
      <MyStoriesPage
        mode="teacher"
        records={[]}
        onDeleteRecord={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: /Materials/ }));
    await user.clear(screen.getByLabelText("Story title"));
    await user.click(screen.getByRole("button", { name: "Save custom story" }));

    expect(screen.getByText("Add a story title for students.")).toBeInTheDocument();
    expect(
      screen.getByText("Frame 1 needs an image URL or uploaded image."),
    ).toBeInTheDocument();
    expect(screen.getByText("No custom stories yet")).toBeInTheDocument();
  });

  it("lets teachers upload a local image for a custom story frame", async () => {
    const user = userEvent.setup();
    render(
      <MyStoriesPage
        mode="teacher"
        records={[]}
        onDeleteRecord={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: /Materials/ }));
    const imageFile = new File(["story-image"], "story-frame.png", {
      type: "image/png",
    });

    await user.upload(screen.getAllByLabelText("Upload from computer")[0], imageFile);
    const imageInputs = screen.getAllByLabelText("Image URL or uploaded file");
    for (let index = 1; index < imageInputs.length; index += 1) {
      await user.type(
        imageInputs[index],
        `https://example.com/upload-support-${index + 1}.jpg`,
      );
    }
    await waitFor(() => {
      const imageInput = screen.getAllByLabelText(
        "Image URL or uploaded file",
      )[0] as HTMLInputElement;
      expect(imageInput.value).toContain("data:image/png");
    });

    await user.click(screen.getByRole("button", { name: "Save custom story" }));
    expect(localStorage.getItem("teacherCustomStories")).toContain(
      "data:image/png",
    );
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
    expect(screen.getByText("1/36")).toBeInTheDocument();
    expect(screen.getByText("Feedback ready")).toBeInTheDocument();

    const firstPrompt = screen.getAllByRole("article")[0];
    expect(
      within(firstPrompt).getByText("Revise with another recording"),
    ).toBeInTheDocument();
    expect(within(firstPrompt).getByText("1 attempt collected")).toBeInTheDocument();
  });
});
