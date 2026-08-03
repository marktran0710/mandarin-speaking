import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TeacherPracticeDebugPage from "./TeacherPracticeDebugPage";
import TeacherDashboardPage from "./TeacherDashboardPage";
import { redactDebugValue } from "../utils/practiceDebug";
import type { AudioRecord } from "./MyStoriesPage";

vi.mock("../utils/audio", () => ({
  convertBlobToWav: vi.fn(async () => new Blob(["wav-audio"], { type: "audio/wav" })),
}));

const runtimeRecord: AudioRecord = {
  id: "attempt-real-1",
  timestamp: "2026-08-03T10:00:00Z",
  duration: 4,
  transcription: "你好",
  model: "ctwhisper",
  topicId: "greetings",
  imageIndex: 0,
  praatMetrics: {
    transcription: "你好",
    transcription_model: "ctwhisper",
    pitch_contour: [[0.1, 180]],
    tone_accuracy: 74,
    fluency_score: 69,
    word_prosody: [{
      token: "你好", tone_accuracy: 54, judged: true, passed: false,
      syllables: [{ char: "你", score: 52 }],
    }],
    feedback_quality: { status: "ok", can_score_pronunciation: true, can_score_content: true },
    ai_feedback: {
      provider: "local",
      vocabulary_coverage: { score: 50 },
      content_accuracy: { score: 75, judged: true, accepted: true },
    },
  },
};

describe("TeacherPracticeDebugPage", () => {
  it("is a distinct destination in the teacher sidebar", async () => {
    const user = userEvent.setup();
    render(
      <TeacherDashboardPage
        records={[runtimeRecord]}
        onDeleteRecord={vi.fn()}
        helpRequests={[]}
        onLogout={vi.fn()}
      />,
    );
    await user.click(screen.getByRole("button", { name: /Practice Debug/ }));
    expect(screen.getByRole("heading", { name: "Practice Stage Debugger" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Practice stage debugger" })).toBeInTheDocument();
  });

  it("shows a runtime attempt and each processing layer", () => {
    render(<TeacherPracticeDebugPage records={[runtimeRecord]} />);
    expect(screen.getByText("Runtime record")).toBeInTheDocument();
    expect(screen.getByText("74%")).toBeInTheDocument();
    expect(screen.getByText("Drill 1 word")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Praat input / output" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "AI / local CAF input and output" })).toBeInTheDocument();
  });

  it("uses the labelled sample when no analyzed runtime records exist", () => {
    render(<TeacherPracticeDebugPage records={[]} />);
    expect(screen.getByText("Transparent sample")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Sample attempt (clearly labelled)" })).toBeInTheDocument();
  });

  it("accepts a pasted analyze response and reports invalid JSON", async () => {
    const user = userEvent.setup();
    render(<TeacherPracticeDebugPage records={[]} />);
    await user.click(screen.getByText("Paste an attempt or /api/analyze response"));
    const input = screen.getByLabelText("Test case JSON");
    await user.type(input, "not json");
    await user.click(screen.getByRole("button", { name: "Inspect JSON" }));
    expect(screen.getByRole("alert")).toBeInTheDocument();
    await user.clear(input);
    fireEvent.change(input, {
      target: { value: JSON.stringify({ transcription: "測試", tone_accuracy: 88, fluency_score: 77 }) },
    });
    await user.click(screen.getByRole("button", { name: "Inspect JSON" }));
    expect(screen.getAllByText("Pasted test case")).toHaveLength(2);
    const summary = screen.getByLabelText("Attempt score summary");
    expect(within(summary).getByText("88%")).toBeInTheDocument();
  });

  it("records a live attempt with the same scene context sent by student practice", async () => {
    const user = userEvent.setup();
    localStorage.setItem("teacherCustomStories", JSON.stringify([{
      id: "debug-story",
      title: "Market visit",
      learningGoal: "Describe the market",
      published: true,
      frames: [{
        imageUrl: "/uploads/market.png",
        prompt: "What is happening at the market?",
        vocabulary: "市場,買菜",
        phrases: "我在市場,我要買菜",
        suggestedAnswer: "我在市場買菜。",
      }],
    }]));

    const stopTrack = vi.fn();
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn(async () => ({ getTracks: () => [{ stop: stopTrack }] })) },
    });
    class MockMediaRecorder {
      static isTypeSupported() { return true; }
      state = "inactive";
      mimeType = "audio/webm";
      ondataavailable: ((event: { data: Blob }) => void) | null = null;
      onstop: (() => void) | null = null;
      start() { this.state = "recording"; }
      stop() {
        this.state = "inactive";
        this.ondataavailable?.({ data: new Blob(["student-voice"], { type: this.mimeType }) });
        this.onstop?.();
      }
    }
    vi.stubGlobal("MediaRecorder", MockMediaRecorder);
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:debug-attempt");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      transcription: "我在市場買菜。",
      tone_accuracy: 83,
      fluency_score: 79,
      processing_trace: {
        stages: [
          { stage: "preflight", status: "review", duration_ms: 12.4, detail: "Sound check passed." },
          { stage: "asr", status: "passed", duration_ms: 820, model: "ctwhisper" },
          { stage: "praat", status: "passed", duration_ms: 140, detail: "Acoustic analysis completed." },
          { stage: "feedback", status: "passed", duration_ms: 310, provider: "local" },
          { stage: "quality_gate", status: "passed", duration_ms: 2 },
        ],
        total_duration_ms: 1284,
      },
      feedback_quality: { can_score_pronunciation: true, can_score_content: true },
      word_prosody: [],
      ai_feedback: { content_accuracy: { judged: true, accepted: true } },
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    render(<TeacherPracticeDebugPage records={[]} />);
    expect(screen.getByRole("combobox", { name: "Published story" })).toHaveValue("teacher-debug-story");
    await user.click(screen.getByRole("button", { name: "Start recording" }));
    await user.click(screen.getByRole("button", { name: /Stop & analyze/ }));

    await waitFor(() => expect(screen.getAllByText("Live debug recording")).toHaveLength(2));
    expect(screen.getByText("83%")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "How this attempt became the result" })).toBeInTheDocument();
    expect(screen.getByText("ASR")).toBeInTheDocument();
    expect(screen.getByText(/Complete · 820 ms/)).toBeInTheDocument();
    expect(screen.getByLabelText("Recorded debug attempt")).toHaveAttribute("src", "blob:debug-attempt");
    expect(stopTrack).toHaveBeenCalled();
    const [, request] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const body = request.body as FormData;
    expect(body.get("asr_model")).toBe("ctwhisper");
    expect(body.get("scene_prompt")).toBe("What is happening at the market?");
    expect(body.get("scene_vocabulary")).toBe("市場, 買菜");
    expect(body.get("scene_phrases")).toBe("我在市場; 我要買菜");
    expect(body.get("scene_suggested_answer")).toBe("我在市場買菜。");
  });

  it("redacts credentials, binaries and signed URL query parameters", () => {
    expect(redactDebugValue({
      api_key: "secret-value",
      Authorization: "Bearer token",
      image_b64: "huge-data",
      imageUrl: "https://example.test/pic.png?token=abc&safe=yes",
    })).toEqual({
      api_key: "[REDACTED]",
      Authorization: "[REDACTED]",
      image_b64: "[binary omitted]",
      imageUrl: "https://example.test/pic.png?token=%5BREDACTED%5D&safe=yes",
    });
  });
});
