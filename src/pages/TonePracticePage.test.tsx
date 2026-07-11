import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TonePracticePage from "./TonePracticePage";

class MockMediaRecorder {
  static isTypeSupported = () => false;

  mimeType = "audio/wav";
  state = "inactive";
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void | Promise<void>) | null = null;

  start() {
    this.state = "recording";
  }

  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["student speech"], { type: "audio/wav" }) });
    void this.onstop?.();
  }
}

function stubAnalyzeResponse(overrides: Record<string, unknown> = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      json: async () => ({
        transcription: "媽",
        transcription_model: "ctwhisper",
        pitch_contour: [
          [0, 180],
          [0.2, 205],
        ],
        word_prosody: [
          {
            token: "媽",
            index: 0,
            start_time: 0,
            end_time: 0.2,
            pitch_contour: [
              [0, 180],
              [0.2, 205],
            ],
            reference_contour: [
              [0, 180],
              [0.2, 205],
            ],
            mean_pitch: 192,
            pitch_range: 25,
            start_pitch: 180,
            end_pitch: 205,
            contour_shape: "level",
            tone_accuracy: 79,
            feedback: "Good match for Tone 1 (flat).",
          },
        ],
        detected_tone: 1,
        tone_accuracy: 79,
        formants: {},
        speech_rate: 3.4,
        fluency_score: 80,
        pitch_statistics: {},
        feedback: "Nice work.",
        recognized_text: null,
        content_match: null,
        ...overrides,
      }),
    })),
  );
}

async function recordOnce(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: /Record$/ }));
  await user.click(screen.getByRole("button", { name: /Stop and see result/ }));
}

describe("TonePracticePage word content verification", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal("MediaRecorder", MockMediaRecorder);
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

  it("does not show a content-mismatch warning when the backend confirms the word matched", async () => {
    stubAnalyzeResponse({ content_match: true, recognized_text: "媽" });
    const user = userEvent.setup();
    render(<TonePracticePage />);

    await recordOnce(user);

    const resultPanel = (await screen.findByText("Good match for Tone 1 (flat).")).closest(
      ".tone-practice-result",
    ) as HTMLElement;
    expect(within(resultPanel).getByText("不錯")).toBeInTheDocument();
    expect(screen.queryByText(/the score above may not be reliable/i)).not.toBeInTheDocument();
  });

  it("shows a content-mismatch warning when the backend says the recording didn't match the target word", async () => {
    stubAnalyzeResponse({ content_match: false, recognized_text: "喝水" });
    const user = userEvent.setup();
    render(<TonePracticePage />);

    await recordOnce(user);

    expect(await screen.findByText(/the score above may not be reliable/i)).toBeInTheDocument();
  });

  it("says nothing about content matching when the backend didn't run verification", async () => {
    stubAnalyzeResponse({ content_match: null, recognized_text: null });
    const user = userEvent.setup();
    render(<TonePracticePage />);

    await recordOnce(user);

    await screen.findByText("Good match for Tone 1 (flat).");
    expect(screen.queryByText(/the score above may not be reliable/i)).not.toBeInTheDocument();
  });

  it("sends verify_word alongside the forced transcription so the backend can check content", async () => {
    stubAnalyzeResponse();
    const user = userEvent.setup();
    render(<TonePracticePage />);

    await recordOnce(user);
    await screen.findByText("Good match for Tone 1 (flat).");

    const requestBody = vi.mocked(globalThis.fetch).mock.calls[0][1]?.body as FormData;
    expect(requestBody.get("transcription")).toBe("媽");
    expect(requestBody.get("verify_word")).toBe("媽");
  });
});
