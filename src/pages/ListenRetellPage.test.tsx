import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Topic } from "../components/TopicSelector";
import { convertBlobToWav } from "../utils/audio";
import ListenRetellPage from "./ListenRetellPage";

vi.mock("../utils/audio", () => ({
  convertBlobToWav: vi.fn(async (blob: Blob) => blob),
}));

const topic = {
  id: "retell-story",
  name: "A market visit",
  description: "Listen and retell",
  skillFocus: "Retelling",
  images: ["/market.png"],
  vocabulary: { 0: ["市場", "買菜"] },
  listenScripts: { 0: "我去市場買菜。" },
} satisfies Topic;

const result = {
  transcription: "我去市場買菜。",
  tone_accuracy: 88,
  fluency_score: 82,
  word_prosody: [{ token: "市", tone_accuracy: 88, feedback: "Good tone." }],
  content_match: true,
  feedback_quality: { status: "reliable", can_score_pronunciation: true, can_score_content: true },
  ai_feedback: {
    provider: "test",
    content_accuracy: {
      score: 86,
      feedback: "Your retelling covers the main idea.",
      matched_details: ["market"],
      missed_details: [],
      judged: true,
    },
  },
};

describe("ListenRetellPage student audio flow", () => {
  beforeEach(() => {
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:listen-retell"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    vi.mocked(convertBlobToWav).mockImplementation(async (blob: Blob) => blob);
    Object.defineProperty(window, "speechSynthesis", {
      configurable: true,
      value: { cancel: vi.fn(), speak: vi.fn() },
    });
    vi.stubGlobal("SpeechSynthesisUtterance", class {
      lang = "";
      rate = 1;
      pitch = 1;
      constructor(public text: string) {}
    });
  });

  it("requires listening first, then stages and analyzes a retelling", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => result });
    vi.stubGlobal("fetch", fetchMock);
    render(<ListenRetellPage publishedTopics={[topic]} />);

    expect(screen.getByText("Listen to the passage at least once before you retell it.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Start retelling/ })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /Listen/ }));
    expect(screen.getByRole("button", { name: /Start retelling/ })).toBeEnabled();

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(["RIFF"], "retell.wav", { type: "audio/wav" }));
    expect(fetchMock).not.toHaveBeenCalled();
    await user.click(screen.getByText("Analyze this audio"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const body = fetchMock.mock.calls[0][1].body as FormData;
    expect(body.get("scene_target_text")).toBe("我去市場買菜。");
    expect(body.get("scene_prompt")).toBe("我去市場買菜。");
    expect(await screen.findByText("Your retelling covers the main idea.")).toBeInTheDocument();
  });

  it("does not let a changed scene reuse the previous recording", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn());
    const secondTopic = { ...topic, id: "second", name: "Second scene", images: ["/second.png"], listenScripts: { 0: "第二段。" } };
    render(<ListenRetellPage publishedTopics={[topic, secondTopic]} />);

    await user.click(screen.getByRole("button", { name: /Listen/ }));
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(["RIFF"], "retell.wav", { type: "audio/wav" }));
    expect(screen.getByText(/Audio ready .*review it, then analyze/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Scene 2/ }));
    expect(screen.queryByText(/Audio ready .*review it, then analyze/)).not.toBeInTheDocument();
    expect(screen.queryByText("Analyze this audio")).not.toBeInTheDocument();
  });

  it("aborts an in-flight retell analysis when the learner changes scene", async () => {
    const user = userEvent.setup();
    const secondTopic = { ...topic, id: "second", name: "Second scene", images: ["/second.png"], listenScripts: { 0: "Second script" } };
    let resolveFetch!: (value: unknown) => void;
    const fetchMock = vi.fn(() => new Promise((resolve) => { resolveFetch = resolve; }));
    vi.stubGlobal("fetch", fetchMock);
    render(<ListenRetellPage publishedTopics={[topic, secondTopic]} />);

    await user.click(screen.getByRole("button", { name: /Listen/ }));
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(["RIFF"], "retell.wav", { type: "audio/wav" }));
    await user.click(screen.getByText("Analyze this audio"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const request = fetchMock.mock.calls[0] as unknown as [RequestInfo | URL, RequestInit];
    const signal = request[1].signal as AbortSignal;

    await user.click(screen.getByRole("button", { name: /Scene 2/ }));
    expect(signal.aborted).toBe(true);
    expect(screen.queryByText("Analyze this audio")).not.toBeInTheDocument();
    resolveFetch({ ok: true, json: async () => result });
  });
});
