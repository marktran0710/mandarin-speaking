import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";

const TEST_BACKEND_URL =
  import.meta.env.VITE_BACKEND_URL || "http://127.0.0.1:8000";

describe("App role flows", () => {
  it("lets a student enter the learning app with the default profile", async () => {
    const user = userEvent.setup();
    render(<App />);

    expect(
      screen.getByRole("heading", { name: "Mandarin Story Coach" }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Student Login" }));
    expect(
      screen.getByRole("heading", { name: "學生登入" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Student name")).toHaveValue("Student Demo");

    await user.click(
      screen.getByRole("button", { name: "Enter Student Mode" }),
    );

    expect(
      screen.getByRole("heading", { name: "Choose a Daily Situation" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "My Stories" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Voice Test" }),
    ).toBeInTheDocument();
  });

  it("opens the student voice test page", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Student Login" }));
    await user.click(
      screen.getByRole("button", { name: "Enter Student Mode" }),
    );
    await user.click(screen.getByRole("button", { name: "Voice Test" }));

    expect(
      screen.getByRole("heading", { name: "Analyze Your Voice" }),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Target sentence")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Import WAV file" }),
    ).toBeInTheDocument();
  });

  it("sends imported WAV files for voice analysis", async () => {
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

    await user.click(screen.getByRole("button", { name: "Student Login" }));
    await user.click(
      screen.getByRole("button", { name: "Enter Student Mode" }),
    );
    await user.click(screen.getByRole("button", { name: "Voice Test" }));

    const input = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    const wavFile = new File(["RIFF....WAVEfmt "], "practice.wave", {
      type: "audio/wave",
    });

    await user.upload(input, wavFile);

    expect(fetchMock).toHaveBeenCalledWith(
      `${TEST_BACKEND_URL}/api/analyze`,
      expect.objectContaining({
        method: "POST",
        body: expect.any(FormData),
      }),
    );
    const requestBody = fetchMock.mock.calls[0][1].body as FormData;
    expect(requestBody.get("transcription")).toBe("");
    expect(requestBody.get("asr_model")).toBe(
      import.meta.env.VITE_VOICE_TEST_ASR_MODEL || "ctwhisper",
    );
    expect(await screen.findByText("practice.wave")).toBeInTheDocument();
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

  it("uses browser speech recognition for live voice test recordings", async () => {
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

    await user.click(screen.getByRole("button", { name: "Student Login" }));
    await user.click(
      screen.getByRole("button", { name: "Enter Student Mode" }),
    );
    await user.click(screen.getByRole("button", { name: "Voice Test" }));
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

  it("opens the teacher dashboard after teacher login", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Teacher Login" }));
    expect(
      screen.getByRole("heading", { name: "教師登入" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Teacher name")).toHaveValue("Teacher Demo");

    await user.click(
      screen.getByRole("button", { name: "Enter Teacher Mode" }),
    );

    expect(
      screen.getByRole("heading", { name: "Class Speaking Dashboard" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Submissions")).toBeInTheDocument();
    expect(screen.getByText("No submissions yet")).toBeInTheDocument();
  });

  it("lets teachers generate six image cues from a situation context", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        provider: "gemini-2.0-flash",
        title: "MRT Help Story",
        learning_goal: "Students describe a problem and ask for help.",
        frames: Array.from({ length: 6 }, (_, index) => ({
          index: index + 1,
          title: `Scene ${index + 1}`,
          student_prompt: `Describe scene ${index + 1}.`,
          vocabulary: ["MRT", "help", "thank you"],
          image_prompt: `Comic scene ${index + 1}`,
          image_url: `data:image/svg+xml,<svg></svg>#${index + 1}`,
        })),
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await user.click(screen.getByRole("button", { name: "Teacher Login" }));
    await user.click(
      screen.getByRole("button", { name: "Enter Teacher Mode" }),
    );
    await user.click(screen.getByRole("button", { name: "Image Builder" }));

    expect(
      screen.getByRole("heading", { name: "Generate Six Picture Cues" }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Generate 6 images" }));

    expect(fetchMock).toHaveBeenCalledWith(
      `${TEST_BACKEND_URL}/api/generate-story-images`,
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
      }),
    );
    expect(
      await screen.findByRole("heading", { name: "MRT Help Story" }),
    ).toBeInTheDocument();
    expect(screen.getAllByAltText(/Generated story frame/)).toHaveLength(6);

    await user.click(
      screen.getByRole("button", { name: "Save to story library" }),
    );

    expect(localStorage.getItem("teacherCustomStories")).toContain(
      "MRT Help Story",
    );
    expect(
      screen.getByText("Generated story saved to the teacher story library."),
    ).toBeInTheDocument();

    vi.unstubAllGlobals();
  });


  it("lets a student raise a hand and a teacher mark the request helped", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Student Login" }));
    await user.click(
      screen.getByRole("button", { name: "Enter Student Mode" }),
    );
    await user.clear(screen.getByLabelText("Help request message"));
    await user.type(
      screen.getByLabelText("Help request message"),
      "Please help me with tones.",
    );
    await user.click(screen.getByRole("button", { name: "Raise hand" }));

    expect(
      screen.getByText("Teacher has your help request"),
    ).toBeInTheDocument();
    expect(localStorage.getItem("helpRequests")).toContain(
      "Please help me with tones.",
    );

    await user.click(screen.getByRole("button", { name: "Log out" }));
    await user.click(screen.getByRole("button", { name: "Teacher Login" }));
    await user.click(
      screen.getByRole("button", { name: "Enter Teacher Mode" }),
    );

    expect(screen.getByText("Student Help Requests")).toBeInTheDocument();
    expect(screen.getByText("Student Demo")).toBeInTheDocument();
    expect(screen.getByText("Please help me with tones.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Mark helped" }));

    expect(screen.getByText("No raised hands")).toBeInTheDocument();
    expect(localStorage.getItem("helpRequests")).toContain("resolved");
  });

  it("persists the active role across reloads", () => {
    localStorage.setItem("activeRole", "teacher");

    render(<App />);

    const overview = screen.getByRole("region", { name: "Class overview" });
    expect(within(overview).getByText("Submissions")).toBeInTheDocument();
  });
});
