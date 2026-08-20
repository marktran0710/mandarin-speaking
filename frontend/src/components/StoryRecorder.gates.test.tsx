import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { UserEvent } from "@testing-library/user-event";
import { waitFor } from "@testing-library/react";
import StoryRecorder from "./StoryRecorder";

vi.setConfig({ testTimeout: 20_000 });

const TEST_BACKEND_URL =
  import.meta.env.VITE_BACKEND_URL || "http://127.0.0.1:8000";

const topic = {
  id: "student-gates-topic",
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
    this.ondataavailable?.({
      data: new Blob(["student speech"], { type: "audio/wav" }),
    });
    void this.onstop?.();
  }
}

function jsonResponse(data: unknown, ok = true) {
  return {
    ok,
    status: ok ? 200 : 500,
    statusText: ok ? "OK" : "Server Error",
    json: async () => data,
  };
}

function buildAnalyzeResponse(overrides: Record<string, unknown> = {}) {
  return {
    transcription: "Student tells the market story",
    transcription_model: "groq",
    pitch_contour: [
      [0, 180],
      [0.2, 205],
      [0.4, 190],
    ],
    word_prosody: [
      {
        token: "市",
        index: 0,
        start_time: 0,
        end_time: 0.2,
        pitch_contour: [
          [0, 210],
          [0.2, 205],
        ],
        reference_contour: [
          [0, 230],
          [0.2, 150],
        ],
        user_curve: [0.7, 0.68],
        target_curve: [0.9, 0.1],
        mean_pitch: 208,
        pitch_range: 5,
        start_pitch: 210,
        end_pitch: 205,
        contour_shape: "level",
        feedback: "Expected falling movement does not match yet.",
        expected_tones: [4],
        tone_accuracy: 57,
        shape_accuracy: 57,
        syllables: [{ char: "市", tone: 4, score: 57, passed: false }],
        passed: false,
      },
    ],
    detected_tone: 2,
    tone_accuracy: 95,
    formants: { F1: 500, F2: 1500, F3: 2500 },
    speech_rate: 3.4,
    fluency_score: 92,
    pitch_statistics: {},
    feedback: "Good start. Keep your tones clear.",
    ai_feedback: {
      provider: "test",
      vocabulary_coverage: {
        score: 100,
        used: ["market"],
        missing: [],
        feedback: "Good vocabulary coverage.",
      },
      coherence: {
        score: 90,
        feedback: "The sentence fits the scene.",
        corrections: [],
      },
      pronunciation_note: {
        score: 70,
        feedback: "Keep the tones crisp.",
        details: [{ key: "tone", text: "Pronunciation detail should be gated." }],
      },
      content_accuracy: {
        score: 90,
        feedback: "The sentence matches the image.",
        matched_details: ["market"],
        missed_details: [],
        accepted: true,
        judged: true,
      },
      corrective_feedback: {
        errors: [],
        hint: "",
        reveal_answer: false,
        correct_version: "",
      },
      improved_version: "Student tells the market story.",
      practice_prompt: "Try again.",
    },
    ...overrides,
  };
}

function mockBackendAnalyze(
  analyze:
    | Record<string, unknown>
    | ((url: string, init?: RequestInit) => Record<string, unknown> | Promise<Record<string, unknown>>),
) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/ai-providers")) {
        return jsonResponse({ providers: [], default: "" });
      }
      if (url.includes("/api/transcribe")) {
        return jsonResponse({ text: "Student tells the market story" });
      }
      if (url.includes("/api/analyze")) {
        const data =
          typeof analyze === "function" ? await analyze(url, init) : analyze;
        return jsonResponse(data);
      }
      return jsonResponse({});
    }),
  );
}

async function uploadVoiceAttempt(
  user: UserEvent,
  fileName = "story-attempt.wav",
  waitForResult = true,
) {
  const voiceFile = new File(["RIFF....WAVEfmt "], fileName, {
    type: "audio/wav",
  });
  const input = document.querySelector(".submit-voice-input") as HTMLInputElement;
  await user.upload(input, voiceFile);
  await user.click(await screen.findByRole("button", { name: /Analyze audio/i }));
  if (waitForResult) {
    await waitFor(() => {
      expect(screen.getByRole("region", { name: "Recording results" })).toBeInTheDocument();
    }, { timeout: 5_000 });
  }
}

describe("StoryRecorder speaking practice gates", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal("MediaRecorder", MockMediaRecorder);
    mockBackendAnalyze(buildAnalyzeResponse());

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

  it("keeps a failing prosody result in the word-practice flow", async () => {
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

    await user.click(screen.getByRole("tab", { name: /Speaking/ }));

    await uploadVoiceAttempt(user, "failed-attempt.wav");

    expect(onAddRecord).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Scene 1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Practice the words/i })).toBeEnabled();
    expect(screen.queryByRole("button", { name: /Next scene/i })).not.toBeInTheDocument();
    expect(screen.queryByText("Scene 2 of 2")).not.toBeInTheDocument();
    expect(globalThis.fetch).toHaveBeenCalledWith(
      `${TEST_BACKEND_URL}/api/analyze`,
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("never unlocks mastery when backend marks pronunciation unscorable", async () => {
    const user = userEvent.setup();
    const base = buildAnalyzeResponse();
    mockBackendAnalyze({
      ...base,
      tone_accuracy: 99,
      fluency_score: 99,
      feedback_quality: {
        status: "retry",
        confidence: 0.05,
        can_score_pronunciation: false,
        can_score_content: false,
        reason_codes: ["silence"],
      },
      word_prosody: [
        {
          ...base.word_prosody[0],
          judged: false,
          passed: null,
          tone_accuracy: 0,
          shape_accuracy: 0,
          syllables: [],
        },
      ],
    });

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

    await user.click(screen.getByRole("tab", { name: /Speaking/ }));
    await uploadVoiceAttempt(user, "silent-attempt.wav");

    expect(
      await screen.findByText("Retake before trusting this score"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Scene 1 complete/i)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Next scene/i }),
    ).not.toBeInTheDocument();
  });

  it("keeps a high-scoring but incomplete script on Fix it and blocks Next scene", async () => {
    const user = userEvent.setup();
    const base = buildAnalyzeResponse();
    mockBackendAnalyze({
      ...base,
      word_prosody: [{
        ...base.word_prosody[0],
        tone_accuracy: 92,
        shape_accuracy: 92,
        passed: true,
        syllables: [{ char: "市", tone: 4, score: 92, passed: true }],
      }],
      ai_feedback: {
        ...base.ai_feedback,
        vocabulary_coverage: {
          score: 50,
          used: ["market"],
          missing: ["help", "friend"],
          feedback: "Include the missing words.",
        },
      },
    });

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

    await user.click(screen.getByRole("tab", { name: /Speaking/ }));
    await uploadVoiceAttempt(user, "incomplete-script.wav");

    expect(await screen.findByRole("button", { name: /See the missing words/i })).toBeEnabled();
    expect(screen.queryByText(/Scene 1 complete/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Next scene/i })).not.toBeInTheDocument();
  });

  it("blocks pronunciation feedback while rejected content is on the fix path", async () => {
    const user = userEvent.setup();
    const base = buildAnalyzeResponse();
    mockBackendAnalyze({
      ...base,
      ai_feedback: {
        ...base.ai_feedback,
        content_accuracy: {
          score: 20,
          feedback: "This describes the wrong scene.",
          matched_details: [],
          missed_details: ["market"],
          accepted: false,
          judged: true,
        },
        corrective_feedback: {
          errors: ["wrong scene"],
          hint: "Mention the market helper before recording again.",
          reveal_answer: false,
          correct_version: "",
        },
      },
    });

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

    await user.click(screen.getByRole("tab", { name: /Speaking/ }));
    await uploadVoiceAttempt(user, "wrong-content.wav");

    await screen.findByRole("region", { name: "Recording results" });
    expect(screen.getByRole("button", { name: /See how to fix it/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Practice the words/ })).not.toBeInTheDocument();
    expect(screen.queryByText("Pronunciation Feedback")).not.toBeInTheDocument();
    expect(screen.queryByText("Pronunciation detail should be gated.")).not.toBeInTheDocument();
  });

  // Was marked `it.fails` with a comment blaming a missing speech-source
  // selector. That diagnosis was wrong: the selector renders fine. What the
  // test could not reach was the "Record again" button, which only existed
  // once the scene had already unlocked — so after one attempt there was no
  // way back to the recorder. Fixing that dead end in SpeakingResultsFlow's
  // footer is what let this pass; see SpeakingResultsFlow.recordAgain.test.tsx.
  it("preserves scene and attempt state across a mid-session speech model switch", async () => {
    const user = userEvent.setup();

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

    await user.click(screen.getByRole("tab", { name: /Speaking/ }));
    const speechSource = screen.getByLabelText(/Speech source/);
    expect(speechSource).toHaveValue("webspeech");

    await uploadVoiceAttempt(user, "before-switch.wav");
    await user.click(screen.getAllByRole("button", { name: /Record again/ })[0]);
    await user.selectOptions(speechSource, "groq");
    await uploadVoiceAttempt(user, "after-switch.wav");

    expect(screen.getByText("Scene 1")).toBeInTheDocument();
  });

  it("shows a visible retry path when speech analysis fails", async () => {
    const user = userEvent.setup();
    mockBackendAnalyze(async (url) => {
      if (url.includes("/api/analyze")) {
        throw new Error("The operation was aborted");
      }
      return buildAnalyzeResponse();
    });

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

    await user.click(screen.getByRole("tab", { name: /Speaking/ }));
    await uploadVoiceAttempt(user, "timeout.wav", false);

    expect(
      await screen.findByText(/Cannot reach the speech analysis backend/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Analyzing recording" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Record$/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Upload audio/ })).toBeInTheDocument();
  });
});
