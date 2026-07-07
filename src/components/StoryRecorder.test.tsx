import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StoryRecorder, { vocabTooltip } from "./StoryRecorder";

vi.mock("../PitchChart", () => ({
  default: () => <div data-testid="pitch-chart">Pitch chart</div>,
}));

vi.mock("./PraatTimeline", () => ({
  default: () => <div data-testid="praat-timeline">Praat timeline</div>,
}));

const topic = {
  id: "student-test-topic",
  name: "Taiwan Market",
  description: "Tell a short story about helping someone at a market.",
  skillFocus: "Story connectors",
  level: "Beginner",
  images: ["https://example.com/market-1.jpg", "https://example.com/market-2.jpg"],
  prompts: ["First prompt", "Second prompt"],
  vocabulary: {
    0: ["market", "help", "friend"],
    1: ["rain", "umbrella"],
  },
};

const TEST_BACKEND_URL = import.meta.env.VITE_BACKEND_URL || "http://127.0.0.1:8000";

let activeRecorder: MockMediaRecorder | null = null;

class MockMediaRecorder {
  static isTypeSupported = () => false;

  mimeType = "audio/wav";
  state = "inactive";
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void | Promise<void>) | null = null;

  constructor() {
    activeRecorder = this;
  }

  start() {
    this.state = "recording";
  }

  stop() {
    this.state = "inactive";
    this.ondataavailable?.({
      data: new Blob(["student speech"], { type: "audio/wav" }),
    });
    void this.onstop?.();
  }
}

describe("vocabTooltip", () => {
  it("combines part of speech and translation", () => {
    expect(vocabTooltip("N", "restaurant")).toBe("(N) restaurant");
  });

  it("returns just the POS in parens when translation is missing", () => {
    expect(vocabTooltip("N", undefined)).toBe("(N)");
  });

  it("returns just the translation when POS is missing", () => {
    expect(vocabTooltip(undefined, "restaurant")).toBe("restaurant");
  });

  it("returns undefined when both are missing", () => {
    expect(vocabTooltip(undefined, undefined)).toBeUndefined();
  });
});

describe("StoryRecorder student prototype", () => {
  beforeEach(() => {
    activeRecorder = null;
    vi.stubGlobal("MediaRecorder", MockMediaRecorder);
    vi.stubGlobal("fetch", vi.fn(async () => {
      return {
        ok: true,
        json: async () => ({
          transcription: "Student tells the market story",
          transcription_model: "ctwhisper",
          pitch_contour: [
            [0, 180],
            [0.2, 205],
            [0.4, 190],
            [0.6, 170],
          ],
          word_prosody: [
            {
              token: "A",
              index: 0,
              start_time: 0,
              end_time: 0.2,
              pitch_contour: [
                [0, 180],
                [0.2, 205],
              ],
              mean_pitch: 192,
              pitch_range: 25,
              start_pitch: 180,
              end_pitch: 205,
              contour_shape: "rising",
              feedback: "Pitch rises clearly.",
            },
            {
              token: "B",
              index: 1,
              start_time: 0.2,
              end_time: 0.4,
              pitch_contour: [
                [0.2, 205],
                [0.4, 190],
              ],
              mean_pitch: 198,
              pitch_range: 15,
              start_pitch: 205,
              end_pitch: 190,
              contour_shape: "level",
              feedback: "Stable pitch.",
            },
          ],
          detected_tone: 2,
          tone_accuracy: 82,
          formants: { F1: 500, F2: 1500, F3: 2500 },
          speech_rate: 3.4,
          fluency_score: 79,
          pitch_statistics: {},
          feedback: "Good start. Keep your tones clear.",
        }),
      };
    }));

    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: vi.fn(async () => ({
          getTracks: () => [{ stop: vi.fn() }],
        })),
      },
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("lets a student build a concept map and receive word-level pronunciation feedback", async () => {
    const user = userEvent.setup();
    const onAddRecord = vi.fn();

    render(
      <StoryRecorder
        topic={topic}
        selectedImage={topic.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={onAddRecord}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "Plan this picture cue" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Student practice flow" }),
    ).toBeInTheDocument();

    await user.type(screen.getByLabelText(/Characters/), "Student A");
    await user.type(screen.getByLabelText(/Place/), "night market");
    await user.type(screen.getByLabelText(/Actions/), "helps a friend");
    await user.click(screen.getByRole("button", { name: "market" }));
    await user.click(screen.getByRole("button", { name: "Draft story from map" }));

    const target = screen.getByText("Pronunciation target").closest("div");
    expect(target).not.toBeNull();
    expect(within(target as HTMLElement).getByText(/Student A/)).toBeInTheDocument();
    expect(within(target as HTMLElement).getByText(/night market/)).toBeInTheDocument();

    await user.click(screen.getByText("Recording options"));
    await user.selectOptions(screen.getByLabelText("Speech source"), "vibevoice");
    await user.click(screen.getByRole("button", { name: "Start recording" }));
    expect(activeRecorder?.state).toBe("recording");

    await user.click(screen.getByRole("button", { name: "Stop and analyze" }));

    await waitFor(() => {
      expect(screen.getByText("Character prosody preview")).toBeInTheDocument();
      expect(screen.getByText("Word-by-word prosody")).toBeInTheDocument();
      expect(screen.getByText("Pitch rises clearly.")).toBeInTheDocument();
    });

    expect(globalThis.fetch).toHaveBeenCalledWith(
      `${TEST_BACKEND_URL}/api/analyze`,
      expect.objectContaining({ method: "POST" }),
    );
    expect(onAddRecord).toHaveBeenCalledWith(
      expect.objectContaining({
        transcription: "Student tells the market story",
        model: "vibevoice",
        praatMetrics: expect.objectContaining({
          word_prosody: expect.any(Array),
        }),
      }),
    );
  });

  it("defaults live recording to browser Traditional Chinese transcription", () => {
    render(
      <StoryRecorder
        topic={topic}
        selectedImage={topic.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={vi.fn()}
      />,
    );

    expect(screen.getByLabelText("Speech source")).toHaveValue("webspeech");
  });

  it("uses Chinese/Taiwanese Whisper when a student submits a voice file", async () => {
    const user = userEvent.setup();
    const onAddRecord = vi.fn();

    render(
      <StoryRecorder
        topic={topic}
        selectedImage={topic.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={onAddRecord}
      />,
    );

    const voiceFile = new File(["RIFF....WAVEfmt "], "story-attempt.wav", {
      type: "audio/wav",
    });
    const input = document.querySelector(
      ".submit-voice-input",
    ) as HTMLInputElement;

    await user.upload(input, voiceFile);

    expect(globalThis.fetch).toHaveBeenCalledWith(
      `${TEST_BACKEND_URL}/api/analyze`,
      expect.objectContaining({ method: "POST" }),
    );
    const requestBody = vi.mocked(globalThis.fetch).mock.calls[0][1]?.body as FormData;
    expect(requestBody.get("transcription")).toBe("");
    expect(requestBody.get("asr_model")).toBe("ctwhisper");
    expect(await screen.findByText("Submitted: story-attempt.wav")).toBeInTheDocument();
    expect(onAddRecord).toHaveBeenCalledWith(
      expect.objectContaining({
        transcription: "Student tells the market story",
        model: "ctwhisper",
      }),
    );
  });

  it("transcribes and analyzes a submitted student voice file with VibeVoice", async () => {
    const user = userEvent.setup();
    const onAddRecord = vi.fn();

    render(
      <StoryRecorder
        topic={topic}
        selectedImage={topic.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={onAddRecord}
      />,
    );

    await user.click(screen.getByText("Recording options"));
    await user.selectOptions(screen.getByLabelText("Speech source"), "vibevoice");

    const voiceFile = new File(["RIFF....WAVEfmt "], "story-attempt.wav", {
      type: "audio/wav",
    });
    const input = document.querySelector(
      ".submit-voice-input",
    ) as HTMLInputElement;

    await user.upload(input, voiceFile);

    expect(globalThis.fetch).toHaveBeenCalledWith(
      `${TEST_BACKEND_URL}/api/analyze`,
      expect.objectContaining({ method: "POST" }),
    );
    const requestBody = vi.mocked(globalThis.fetch).mock.calls[0][1]?.body as FormData;
    expect(requestBody.get("transcription")).toBe("");
    expect(requestBody.get("asr_model")).toBe("vibevoice");
    expect(await screen.findByText("Submitted: story-attempt.wav")).toBeInTheDocument();
    expect(
      (await screen.findAllByText("Student tells the market story")).length,
    ).toBeGreaterThan(0);
    expect(onAddRecord).toHaveBeenCalledWith(
      expect.objectContaining({
        transcription: "Student tells the market story",
        model: "vibevoice",
      }),
    );
  });

  it("shows the sorting challenge when enableSorting is true and allows skipping it", async () => {
    const onAddRecord = vi.fn();
    const user = userEvent.setup();

    render(
      <StoryRecorder
        topic={topic}
        selectedImage={topic.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={onAddRecord}
        enableSorting={true}
      />,
    );

    // Verify sorting challenge is shown
    expect(screen.getByText("Arrange the Story Scenes")).toBeInTheDocument();
    expect(screen.queryByText("Recording options")).not.toBeInTheDocument();

    // Verify prompts are rendered as hints
    expect(screen.getByText("First prompt")).toBeInTheDocument();
    expect(screen.getByText("Second prompt")).toBeInTheDocument();

    // Click Skip Challenge to unlock standard UI
    await user.click(screen.getByRole("button", { name: "Skip Challenge" }));

    // Verify it unlocks the standard recording UI
    expect(screen.queryByText("Arrange the Story Scenes")).not.toBeInTheDocument();
    expect(screen.getByText("Recording options")).toBeInTheDocument();
  });
});

