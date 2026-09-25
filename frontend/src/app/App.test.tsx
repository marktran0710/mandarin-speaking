import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import App, { getStudentAppBootstrapState } from "./App";

vi.setConfig({ testTimeout: 15000 });

const TEST_BACKEND_URL =
  import.meta.env.VITE_BACKEND_URL || "http://127.0.0.1:8000";

describe("App role flows", () => {
  it("bootstraps a returning student into the saved workspace before effects run", () => {
    localStorage.setItem(
      "studentSession",
      JSON.stringify({
        role: "student",
        name: "Ada",
        signedInAt: "2026-01-01T00:00:00.000Z",
      }),
    );
    localStorage.setItem("studentLastPage:ada", "student-stories");

    expect(getStudentAppBootstrapState()).toMatchObject({
      activeRole: "student",
      currentPage: "student-workspace",
      studentWorkspaceView: "progress",
      practiceTarget: null,
    });
  });

  it("gives a signed-in student diagnostic URLs precedence over saved navigation", () => {
    localStorage.setItem(
      "studentSession",
      JSON.stringify({
        role: "student",
        name: "Ada",
        signedInAt: "2026-01-01T00:00:00.000Z",
      }),
    );
    localStorage.setItem("studentLastPage:ada", "student-stories");
    window.history.pushState({}, "", "/voice-test");

    expect(getStudentAppBootstrapState()).toMatchObject({
      activeRole: "student",
      currentPage: "voice-test",
    });

    window.history.pushState({}, "", "/");
  });

  it("gives a signed-in student the placement-test URL precedence over saved navigation", () => {
    localStorage.setItem(
      "studentSession",
      JSON.stringify({
        role: "student",
        name: "Ada",
        signedInAt: "2026-01-01T00:00:00.000Z",
      }),
    );
    localStorage.setItem("studentLastPage:ada", "student-stories");
    window.history.pushState({}, "", "/placement-test");

    expect(getStudentAppBootstrapState()).toMatchObject({
      activeRole: "student",
      currentPage: "placement-test",
    });

    window.history.pushState({}, "", "/");
  });

  it("gives a signed-in student the listen-and-retell URL precedence over saved navigation", () => {
    localStorage.setItem(
      "studentSession",
      JSON.stringify({
        role: "student",
        name: "Ada",
        signedInAt: "2026-01-01T00:00:00.000Z",
      }),
    );
    localStorage.setItem("studentLastPage:ada", "student-stories");
    window.history.pushState({}, "", "/listen-retell");

    expect(getStudentAppBootstrapState()).toMatchObject({
      activeRole: "student",
      currentPage: "listen-retell",
    });

    window.history.pushState({}, "", "/");
  });

  it("replaces the pre-login history entry on login, so Back out of a story doesn't bounce to the marketing page", async () => {
    // Before this fix: the browser history entry created on first mount
    // (while logged out) keeps its "home" snapshot forever, because
    // handleLogin only updates React state. Once a story pushes one more
    // history entry, a single Back from that story pops straight to the
    // stale pre-login "home" entry — landing a signed-in student back on
    // the anonymous marketing page instead of their workspace.
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/api/students/login")) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            id: "student-1",
            name: "Student Demo",
            createdAt: "2026-01-01T00:00:00.000Z",
            status: "active",
          }),
        } as Response;
      }
      return { ok: false, status: 404, json: async () => ({}) } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await user.click(screen.getByRole("button", { name: /Student Login/ }));
    await user.type(screen.getByLabelText(/Student name/), "Student Demo");
    await user.type(screen.getByLabelText(/Password/), "123456");
    await user.click(
      screen.getByRole("button", { name: /Enter Student Mode/ }),
    );

    await waitFor(() => {
      expect(
        (window.history.state as Record<string, unknown> | null)
          ?.mandarinApp,
      ).toMatchObject({ currentPage: "student-workspace" });
    });

    vi.unstubAllGlobals();
  });

  it("moves from the public landing page into the learner workspace", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        id: "student-app-flow",
        name: "App Flow Student",
        createdAt: "2026-08-22T00:00:00.000Z",
        status: "active",
      }),
    } as Response);
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await user.click(screen.getByRole("button", { name: /Start Learning/ }));
    await user.type(screen.getByLabelText(/Student name/), "App Flow Student");
    await user.type(screen.getByLabelText(/Password/), "123456");
    await user.click(screen.getByRole("button", { name: /Enter Student Mode/ }));

    expect(await screen.findByText("App Flow Student", { selector: ".sa-sidebar__identity-name" })).toBeInTheDocument();

    vi.unstubAllGlobals();
  });

  it.skip("lets a student enter the learning app with the default profile", async () => {
    const user = userEvent.setup();
    render(<App />);

    expect(
      screen.getByRole("heading", { name: /Mandarin, little by little/ }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Student Login/ }));
    expect(
      screen.getByRole("heading", { name: "學生登入" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/Student name/)).toHaveValue("Student Demo");

    await user.click(
      screen.getByRole("button", { name: /Enter Student Mode/ }),
    );

    expect(
      screen.getByRole("heading", { name: /Choose|Daily|Situation|Learn/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /My Profile/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Voice Test/ }),
    ).toBeInTheDocument();
  });

  it.skip("opens the student voice test page", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: /Student Login/ }));
    await user.type(screen.getByLabelText(/Student name/), "Student Demo");
    await user.type(screen.getByLabelText(/Password/), "123456");
    await user.click(
      screen.getByRole("button", { name: /Enter Student Mode/ }),
    );
    await user.click(screen.getByRole("button", { name: /Voice Test/ }));

    expect(
      screen.getByRole("heading", { name: /Analyze Your Voice/ }),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Target sentence")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Import WAV file/ }),
    ).toBeInTheDocument();
  });

  it.skip("sends imported WAV files for voice analysis", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        description:
          "The system transcribed your recording and found 1 word-level prosody item for review.",
        transcription: "今天下雨，我和朋友一起回家。",
        transcription_model: "auto:ctwhisper",
        pitch_contour: [
          [0.1, 180],
          [0.2, 205],
          [0.3, 220],
        ],
        word_prosody: [
          {
            token: "今",
            index: 0,
            start_time: 0,
            end_time: 0.15,
            pitch_contour: [[0.1, 180]],
            mean_pitch: 180,
            pitch_range: 12,
            start_pitch: 178,
            end_pitch: 190,
            contour_shape: "rising",
            feedback: "Pitch rises clearly.",
          },
        ],
        detected_tone: 1,
        tone_accuracy: 80,
        speech_rate: 2.5,
        fluency_score: 75,
        feedback: "Good start.",
        ai_feedback: {
          provider: "local",
          fluency: { score: 75, feedback: "Keep a steady pace." },
          grammar: { score: 75, feedback: "Clear sentence.", corrections: [] },
          vocabulary: { score: 75, feedback: "Useful words.", suggestions: [] },
          improved_version: "今天下雨，我和朋友一起回家。",
          practice_prompt: "Try again with a smooth ending.",
        },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    await user.click(screen.getByRole("button", { name: /Student Login/ }));
    await user.type(screen.getByLabelText(/Student name/), "Student Demo");
    await user.type(screen.getByLabelText(/Password/), "123456");
    await user.click(
      screen.getByRole("button", { name: /Enter Student Mode/ }),
    );
    await user.click(screen.getByRole("button", { name: /Voice Test/ }));

    const input = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    const wavFile = new File(["RIFF....WAVEfmt "], "practice.wave", {
      type: "audio/wave",
    });

    await user.upload(input, wavFile);

    expect(fetchMock).not.toHaveBeenCalled();
    await user.click(screen.getByText("Analyze this audio"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      `${TEST_BACKEND_URL}/api/analyze`,
      expect.objectContaining({
        method: "POST",
        body: expect.any(FormData),
      }),
    ));
    const requestBody = fetchMock.mock.calls[0][1].body as FormData;
    expect(requestBody.get("transcription")).toBe("");
    expect(requestBody.get("asr_model")).toBe(
      import.meta.env.VITE_VOICE_TEST_ASR_MODEL || "ctwhisper",
    );
    expect(await screen.findByText(/practice\.wave/)).toBeInTheDocument();
    expect(
      await screen.findByText(
        "The system transcribed your recording and found 1 word-level prosody item for review.",
      ),
    ).toBeInTheDocument();
    expect(
      (await screen.findAllByText("今天下雨，我和朋友一起回家。")).length,
    ).toBeGreaterThanOrEqual(2);
    expect(screen.getByLabelText("Word-level script")).toBeInTheDocument();
    expect(screen.getAllByText("Rising").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/180 Hz/).length).toBeGreaterThan(0);
    expect(
      screen.getByRole("heading", { name: "Praat visualization" }),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText(
        "Praat style waveform, pitch contour, and word timeline",
      ),
    ).toBeInTheDocument();

    vi.unstubAllGlobals();
  });

  it.skip("uses browser speech recognition for live voice test recordings", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        description:
          "The system used your browser transcript and found 2 word-level prosody items for review.",
        transcription: "今天下雨",
        transcription_model: "",
        pitch_contour: [
          [0.1, 180],
          [0.2, 205],
        ],
        word_prosody: [],
        detected_tone: 1,
        tone_accuracy: 80,
        speech_rate: 2.5,
        fluency_score: 75,
        feedback: "Good start.",
        ai_feedback: {
          provider: "local",
          fluency: { score: 75, feedback: "Keep a steady pace." },
          grammar: { score: 75, feedback: "Clear sentence.", corrections: [] },
          vocabulary: { score: 75, feedback: "Useful words.", suggestions: [] },
          improved_version: "今天下雨。",
          practice_prompt: "Try again with a smooth ending.",
        },
      }),
    });
    let activeRecorder: {
      state: string;
      ondataavailable: ((event: { data: Blob }) => void) | null;
      onstop: (() => void | Promise<void>) | null;
      stop: () => void;
    } | null = null;

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

    class MockSpeechRecognition {
      continuous = false;
      interimResults = false;
      lang = "";
      onresult: ((event: any) => void) | null = null;

      start() {
        const result: any = [{ transcript: "今天下雨" }];
        result.isFinal = true;
        setTimeout(() => {
          this.onresult?.({
            resultIndex: 0,
            results: [result],
          });
        }, 0);
      }

      stop() {}
    }

    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("MediaRecorder", MockMediaRecorder);
    vi.stubGlobal("SpeechRecognition", MockSpeechRecognition);
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: vi.fn(async () => ({
          getTracks: () => [{ stop: vi.fn() }],
        })),
      },
    });

    render(<App />);

    await user.click(screen.getByRole("button", { name: /Student Login/ }));
    await user.type(screen.getByLabelText(/Student name/), "Student Demo");
    await user.type(screen.getByLabelText(/Password/), "123456");
    await user.click(
      screen.getByRole("button", { name: /Enter Student Mode/ }),
    );
    await user.click(screen.getByRole("button", { name: /Voice Test/ }));
    await user.click(screen.getByRole("button", { name: "Start voice test" }));

    expect((activeRecorder as { state: string } | null)?.state).toBe(
      "recording",
    );
    expect(await screen.findByText("今天下雨")).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: "Stop and get feedback" }),
    );

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        `${TEST_BACKEND_URL}/api/analyze`,
        expect.objectContaining({
          method: "POST",
          body: expect.any(FormData),
        }),
      );
    });
    const requestBody = fetchMock.mock.calls[0][1].body as FormData;
    expect(requestBody.get("transcription")).toBe("今天下雨");
    expect(requestBody.get("asr_model")).toBeNull();

    vi.unstubAllGlobals();
  });

});
