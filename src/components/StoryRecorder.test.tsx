import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StoryRecorder from "./StoryRecorder";

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
  vocabulary: {
    0: ["market", "help", "friend"],
    1: ["rain", "umbrella"],
  },
};

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

describe("StoryRecorder student prototype", () => {
  beforeEach(() => {
    activeRecorder = null;
    vi.stubGlobal("MediaRecorder", MockMediaRecorder);
    vi.stubGlobal("fetch", vi.fn(async () => {
      return {
        ok: true,
        json: async () => ({
          transcription: "學生在市場幫朋友",
          transcription_model: "vibevoice",
          pitch_contour: [
            [0, 180],
            [0.2, 205],
            [0.4, 190],
            [0.6, 170],
          ],
          word_prosody: [
            {
              token: "學",
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
              token: "生",
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
      `${import.meta.env.VITE_BACKEND_URL}/api/analyze`,
      expect.objectContaining({ method: "POST" }),
    );
    expect(onAddRecord).toHaveBeenCalledWith(
      expect.objectContaining({
        transcription: "學生在市場幫朋友",
        model: "vibevoice",
        praatMetrics: expect.objectContaining({
          word_prosody: expect.any(Array),
        }),
      }),
    );
  });
});
