import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Topic } from "../components/TopicSelector";
import { convertBlobToWav } from "../utils/audio";
import ImageNarrationPage from "./ImageNarrationPage";

vi.mock("../utils/audio", () => ({
  convertBlobToWav: vi.fn(async (blob: Blob) => blob),
}));

const topic = {
  id: "picture-story",
  name: "At the park",
  description: "Describe a park scene",
  skillFocus: "Speaking",
  images: ["/park.png"],
  prompts: ["Describe what is happening in the park."],
  vocabulary: { 0: ["朋友", "公園"] },
} satisfies Topic;

const successfulResult = {
  transcription: "朋友在公園。",
  tone_accuracy: 86,
  fluency_score: 80,
  word_prosody: [{ token: "朋", tone_accuracy: 86, feedback: "Clear tone." }],
  content_match: true,
  feedback_quality: {
    status: "reliable",
    can_score_pronunciation: true,
    can_score_content: true,
  },
  ai_feedback: {
    provider: "test",
    content_accuracy: {
      score: 84,
      feedback: "The description matches the picture.",
      matched_details: ["park"],
      missed_details: [],
      judged: true,
    },
    vocabulary_coverage: {
      score: 80,
      used: ["公園"],
      missing: [],
      feedback: "Good keyword use.",
    },
  },
};

describe("ImageNarrationPage student audio flow", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:image-narration"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    vi.mocked(convertBlobToWav).mockImplementation(async (blob: Blob) => blob);
  });

  it("stages an uploaded audio file and only submits after Analyze", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => successfulResult,
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<ImageNarrationPage publishedTopics={[topic]} />);

    expect(screen.getByRole("heading", { name: /Describe the Picture/ })).toBeInTheDocument();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(["RIFF"], "park.wav", { type: "audio/wav" }));

    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByText(/Audio ready .*review it, then analyze/)).toBeInTheDocument();
    await user.click(screen.getByText("Analyze this audio"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const body = fetchMock.mock.calls[0][1].body as FormData;
    expect(body.get("scene_prompt")).toBe("Describe what is happening in the park.");
    expect(body.get("scene_image_url")).toBe("/park.png");
    expect(body.get("scene_vocabulary")).toBe("朋友, 公園");
    expect(await screen.findByText("The description matches the picture.")).toBeInTheDocument();
    expect(screen.getByText("Content accuracy")).toBeInTheDocument();
  });

  it("rejects non-audio uploads without calling the backend", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<ImageNarrationPage publishedTopics={[topic]} />);

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [new File(["not audio"], "notes.txt", { type: "text/plain" })] },
    });

    expect(screen.getByText("Please choose an audio file.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.queryByText("Analyze this audio")).not.toBeInTheDocument();
  });

  it("shows a safe retry state and hides score details for an unscorable result", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ...successfulResult,
        feedback_quality: {
          status: "retry",
          can_score_pronunciation: false,
          can_score_content: false,
          student_message: "Please say the sentence once more.",
        },
      }),
    }));
    render(<ImageNarrationPage publishedTopics={[topic]} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(["RIFF"], "park.wav", { type: "audio/wav" }));
    await user.click(screen.getByText("Analyze this audio"));

    expect(await screen.findByRole("alert")).toHaveTextContent("Please say the sentence once more.");
    expect(screen.queryByText("Content accuracy")).not.toBeInTheDocument();
  });

  it("aborts an in-flight analysis when the learner changes scene", async () => {
    const user = userEvent.setup();
    const secondTopic = { ...topic, id: "second", name: "At the market", images: ["/market.png"], prompts: ["Describe the market."] };
    let resolveFetch!: (value: unknown) => void;
    const fetchMock = vi.fn(() => new Promise((resolve) => { resolveFetch = resolve; }));
    vi.stubGlobal("fetch", fetchMock);
    render(<ImageNarrationPage publishedTopics={[topic, secondTopic]} />);

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(["RIFF"], "park.wav", { type: "audio/wav" }));
    await user.click(screen.getByText("Analyze this audio"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const request = fetchMock.mock.calls[0] as unknown as [RequestInfo | URL, RequestInit];
    const signal = request[1].signal as AbortSignal;

    await user.click(screen.getByRole("button", { name: /Scene 2/ }));
    expect(signal.aborted).toBe(true);
    expect(screen.queryByText("Analyze this audio")).not.toBeInTheDocument();
    resolveFetch({ ok: true, json: async () => successfulResult });
  });

  it("does not render a missing numeric score as NaN", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ...successfulResult, tone_accuracy: undefined }),
    }));
    render(<ImageNarrationPage publishedTopics={[topic]} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(["RIFF"], "park.wav", { type: "audio/wav" }));
    await user.click(screen.getByText("Analyze this audio"));

    await screen.findByText("The description matches the picture.");
    expect(screen.queryByText("NaN")).not.toBeInTheDocument();
    expect(screen.queryByText("Tone accuracy")).not.toBeInTheDocument();
  });

  it("drops a recording that is stopped by a scene change", async () => {
    const user = userEvent.setup();
    const tracks = [{ stop: vi.fn() }];
    const stream = { getTracks: () => tracks };
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn(async () => stream) },
    });
    class TestMediaRecorder {
      static isTypeSupported = () => true;
      state = "inactive";
      mimeType = "audio/webm";
      ondataavailable: ((event: { data: Blob }) => void) | null = null;
      onstop: (() => void) | null = null;
      start() { this.state = "recording"; }
      stop() { this.state = "inactive"; this.onstop?.(); }
    }
    vi.stubGlobal("MediaRecorder", TestMediaRecorder);
    render(<ImageNarrationPage publishedTopics={[topic, { ...topic, id: "second", images: ["/second.png"] }]} />);

    await user.click(screen.getByRole("button", { name: /Start describing/ }));
    await user.click(screen.getByRole("button", { name: /Scene 2/ }));

    expect(tracks[0].stop).toHaveBeenCalled();
    expect(screen.queryByText("Analyze this audio")).not.toBeInTheDocument();
    expect(screen.queryByText(/Audio ready/)).not.toBeInTheDocument();
  });
});
