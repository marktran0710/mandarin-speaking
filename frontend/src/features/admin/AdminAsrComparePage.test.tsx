import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AdminAsrComparePage from "./AdminAsrComparePage";

vi.mock("@entities/audio", () => ({
  convertBlobToWav: vi.fn(async () => new Blob(["wav-audio"], { type: "audio/wav" })),
}));

function buildStreamResponse(stages: Array<Record<string, unknown>>, result: Record<string, unknown>) {
  const lines = [
    ...stages.map((stage) => `data: ${JSON.stringify({ type: "stage", ...stage })}\n\n`),
    `data: ${JSON.stringify({ type: "result", result })}\n\n`,
  ];
  return new Response(lines.join(""), { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

function resultFor(model: string, transcription: string, toneAccuracy: number) {
  return {
    transcription,
    tone_accuracy: toneAccuracy,
    fluency_score: 80,
    processing_trace: {
      total_duration_ms: 900,
      stages: [
        { stage: "preflight", status: "review", duration_ms: 5 },
        { stage: "asr", status: "passed", duration_ms: 700, model },
        { stage: "praat", status: "passed", duration_ms: 150 },
        { stage: "feedback", status: "passed", duration_ms: 40, provider: "local" },
        { stage: "quality_gate", status: "passed", duration_ms: 2 },
      ],
    },
    feedback_quality: { can_score_pronunciation: true, can_score_content: true },
    word_prosody: [],
    ai_feedback: { content_accuracy: { judged: true, accepted: true } },
  };
}

function mockFetchWithPerModelResults() {
  return vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
    const body = init?.body as FormData;
    const model = String(body.get("asr_model"));
    if (model === "ctwhisper") {
      const result = resultFor("ctwhisper", "你好", 70);
      return buildStreamResponse(result.processing_trace.stages, result);
    }
    if (model === "openai") {
      const result = resultFor("openai", "你好嗎", 92);
      return buildStreamResponse(result.processing_trace.stages, result);
    }
    throw new Error(`Unexpected asr_model: ${model}`);
  });
}

describe("AdminAsrComparePage", () => {
  it("runs the same recording through both models in parallel and shows both real results", async () => {
    const user = userEvent.setup();
    const fetchMock = mockFetchWithPerModelResults();
    vi.stubGlobal("fetch", fetchMock);

    render(<AdminAsrComparePage />);
    const file = new File(["sample-audio"], "sample.wav", { type: "audio/wav" });
    await user.upload(screen.getByLabelText("Upload audio file to compare"), file);

    // The quick-comparison table is the primary place these are checked —
    // the same numbers also appear in the two full pipeline views below it.
    await waitFor(() => expect(screen.getByRole("table")).toHaveTextContent("70%"));
    const table = screen.getByRole("table");
    expect(table).toHaveTextContent("92%");
    expect(table).toHaveTextContent("你好");
    expect(table).toHaveTextContent("你好嗎");

    const analyzeCalls = fetchMock.mock.calls.filter(([url]) => String(url).includes("/api/analyze/stream"));
    expect(analyzeCalls).toHaveLength(2);
    const models = analyzeCalls.map(([, init]) => (init?.body as FormData).get("asr_model")).sort();
    expect(models).toEqual(["ctwhisper", "openai"]);

    // Transcripts differ ("你好" vs "你好嗎") — the mismatch banner must say so.
    expect(screen.getByText(/Transcripts differ between models/)).toBeInTheDocument();
  });

  it("shows an error in one column without losing the other model's result", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      const body = init?.body as FormData;
      const model = String(body.get("asr_model"));
      if (model === "openai") return new Response("boom", { status: 500 });
      const result = resultFor("ctwhisper", "你好", 70);
      return buildStreamResponse(result.processing_trace.stages, result);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<AdminAsrComparePage />);
    const file = new File(["sample-audio"], "sample.wav", { type: "audio/wav" });
    await user.upload(screen.getByLabelText("Upload audio file to compare"), file);

    await waitFor(() => expect(screen.getByRole("table")).toHaveTextContent("70%"));
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("rejects a non-audio file before calling the backend", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(<AdminAsrComparePage />);
    const file = new File(["not audio"], "notes.txt", { type: "text/plain" });
    const input = screen.getByLabelText("Upload audio file to compare");
    // userEvent.upload filters against the input's `accept` attribute like a
    // real file picker would; firing the change event directly bypasses that
    // so this test can exercise the component's own extension/MIME check.
    Object.defineProperty(input, "files", { value: [file] });
    fireEvent.change(input);

    expect(await screen.findByText(/Choose an audio file/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
