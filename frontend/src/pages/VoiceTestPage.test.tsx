import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import VoiceTestPage from "./VoiceTestPage";

vi.mock("../utils/audio", () => ({
  convertBlobToWav: vi.fn(async (blob: Blob) => blob),
}));

const metrics = {
  description: "The recording is clear.",
  transcription: "你好。",
  transcription_model: "ctwhisper",
  pitch_contour: [[0.1, 180], [0.2, 190]],
  word_prosody: [{
    token: "你",
    index: 0,
    mean_pitch: 180,
    pitch_range: 12,
    contour_shape: "falling",
    feedback: "Keep the ending steady.",
  }],
  detected_tone: 3,
  tone_accuracy: 84,
  speech_rate: 2.2,
  fluency_score: 78,
  feedback: "Good start.",
  feedback_quality: { status: "reliable", can_score_pronunciation: true, can_score_content: true },
};

describe("VoiceTestPage student audio flow", () => {
  beforeEach(() => {
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:voice-test"),
    });
  });

  it("keeps an imported WAV staged until the learner explicitly analyzes it", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => metrics });
    vi.stubGlobal("fetch", fetchMock);
    render(<VoiceTestPage />);

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(["RIFF"], "voice.wav", { type: "audio/wav" }));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByText(/Audio ready .*review it, then analyze/)).toBeInTheDocument();
    await user.click(screen.getByText("Analyze this audio"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const body = fetchMock.mock.calls[0][1].body as FormData;
    expect(body.get("transcription")).toBe("");
    expect(body.get("asr_model")).toBe("ctwhisper");
    expect(await screen.findByText("The recording is clear.")).toBeInTheDocument();
    expect(screen.getByText("ASR model: ctwhisper")).toBeInTheDocument();
  });

  it("rejects unsupported file types before any analysis request", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<VoiceTestPage />);

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [new File(["MP3"], "voice.mp3", { type: "audio/mpeg" })] },
    });
    expect(screen.getByText(/voice.mp3.*not supported yet/i)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.queryByText("Analyze this audio")).not.toBeInTheDocument();
  });
});
