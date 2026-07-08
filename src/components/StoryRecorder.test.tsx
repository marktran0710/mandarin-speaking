import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { UserEvent } from "@testing-library/user-event";
import StoryRecorder, { vocabTooltip } from "./StoryRecorder";

/** Picks Free Practice mode (if the mode-select screen is showing), answers
 * one question of the vocabulary quiz (any option — this is about reaching
 * the end, not scoring), then finishes the run — Free mode is unlimited, so
 * there's no natural last question — and continues past the results screen.
 * Required to advance past a first-time (skip-not-yet-unlocked) quiz. */
async function completeVocabQuiz(user: UserEvent) {
  const freeModeButton = screen.queryByRole("button", { name: /Free Practice/ });
  if (freeModeButton) await user.click(freeModeButton);

  const optionsGroup = screen.queryByRole("group", { name: /What does/ });
  if (optionsGroup) {
    const firstOption = within(optionsGroup).getAllByRole("button")[0];
    await user.click(firstOption);
    await user.click(screen.getByRole("button", { name: /Finish & see results/ }));
  }

  const continueButton = screen.queryByRole("button", { name: /Continue to practice/ });
  if (continueButton) await user.click(continueButton);
}

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
  prompts: ["First prompt", "Second prompt"],
  vocabulary: {
    0: ["market", "help", "friend"],
    1: ["rain", "umbrella"],
  },
};

const topicWithVocabDetails = {
  ...topic,
  vocabulary: {
    0: ["market", "help"],
  },
  vocabularyPinyin: {
    0: ["shìchǎng", "bāngmáng"],
  },
  vocabularyPos: {
    0: ["N", "V"],
  },
  vocabularyTranslation: {
    0: ["marketplace", ""],
  },
};

const topicWithQuizVocab = {
  ...topic,
  vocabulary: {
    0: ["market", "help", "friend"],
  },
  vocabularyTranslation: {
    0: ["marketplace", "to help", "friend"],
  },
};

const TEST_BACKEND_URL = import.meta.env.VITE_BACKEND_URL || "http://127.0.0.1:8000";

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

describe("vocabTooltip", () => {
  it("combines part of speech and translation", () => {
    expect(vocabTooltip("N", "restaurant")).toBe("(N) restaurant");
  });

  it("returns just the POS in parens when translation is missing", () => {
    expect(vocabTooltip("N", undefined)).toBe("(N)");
  });

  it("returns just the translation when POS is missing", () => {
    expect(vocabTooltip(undefined, "restaurant")).toBe("restaurant");
  });

  it("returns undefined when both are missing", () => {
    expect(vocabTooltip(undefined, undefined)).toBeUndefined();
  });
});

describe("StoryRecorder student prototype", () => {
  beforeEach(() => {
    localStorage.clear();
    activeRecorder = null;
    vi.stubGlobal("MediaRecorder", MockMediaRecorder);
    vi.stubGlobal("fetch", vi.fn(async () => {
      return {
        ok: true,
        json: async () => ({
          transcription: "Student tells the market story",
          transcription_model: "ctwhisper",
          pitch_contour: [
            [0, 180],
            [0.2, 205],
            [0.4, 190],
            [0.6, 170],
          ],
          word_prosody: [
            {
              token: "A",
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
              token: "B",
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
      `${TEST_BACKEND_URL}/api/analyze`,
      expect.objectContaining({ method: "POST" }),
    );
    expect(onAddRecord).toHaveBeenCalledWith(
      expect.objectContaining({
        transcription: "Student tells the market story",
        model: "vibevoice",
        praatMetrics: expect.objectContaining({
          word_prosody: expect.any(Array),
        }),
      }),
    );
  });

  it("defaults live recording to browser Traditional Chinese transcription", () => {
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

    expect(screen.getByLabelText("Speech source")).toHaveValue("webspeech");
  });

  it("uses Chinese/Taiwanese Whisper when a student submits a voice file", async () => {
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

    const voiceFile = new File(["RIFF....WAVEfmt "], "story-attempt.wav", {
      type: "audio/wav",
    });
    const input = document.querySelector(
      ".submit-voice-input",
    ) as HTMLInputElement;

    await user.upload(input, voiceFile);

    expect(globalThis.fetch).toHaveBeenCalledWith(
      `${TEST_BACKEND_URL}/api/analyze`,
      expect.objectContaining({ method: "POST" }),
    );
    const requestBody = vi.mocked(globalThis.fetch).mock.calls[0][1]?.body as FormData;
    expect(requestBody.get("transcription")).toBe("");
    expect(requestBody.get("asr_model")).toBe("ctwhisper");
    expect(await screen.findByText("Submitted: story-attempt.wav")).toBeInTheDocument();
    expect(onAddRecord).toHaveBeenCalledWith(
      expect.objectContaining({
        transcription: "Student tells the market story",
        model: "ctwhisper",
      }),
    );
  });

  it("transcribes and analyzes a submitted student voice file with VibeVoice", async () => {
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

    await user.click(screen.getByText("Recording options"));
    await user.selectOptions(screen.getByLabelText("Speech source"), "vibevoice");

    const voiceFile = new File(["RIFF....WAVEfmt "], "story-attempt.wav", {
      type: "audio/wav",
    });
    const input = document.querySelector(
      ".submit-voice-input",
    ) as HTMLInputElement;

    await user.upload(input, voiceFile);

    expect(globalThis.fetch).toHaveBeenCalledWith(
      `${TEST_BACKEND_URL}/api/analyze`,
      expect.objectContaining({ method: "POST" }),
    );
    const requestBody = vi.mocked(globalThis.fetch).mock.calls[0][1]?.body as FormData;
    expect(requestBody.get("transcription")).toBe("");
    expect(requestBody.get("asr_model")).toBe("vibevoice");
    expect(await screen.findByText("Submitted: story-attempt.wav")).toBeInTheDocument();
    expect(
      (await screen.findAllByText("Student tells the market story")).length,
    ).toBeGreaterThan(0);
    expect(onAddRecord).toHaveBeenCalledWith(
      expect.objectContaining({
        transcription: "Student tells the market story",
        model: "vibevoice",
      }),
    );
  });

  it("shows the sorting challenge when enableSorting is true and allows skipping it", async () => {
    const onAddRecord = vi.fn();
    const user = userEvent.setup();

    render(
      <StoryRecorder
        topic={topic}
        selectedImage={topic.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={onAddRecord}
        enableSorting={true}
      />,
    );

    // Verify sorting challenge is shown
    expect(screen.getByText("Arrange the Story Scenes")).toBeInTheDocument();
    expect(screen.queryByText("Recording options")).not.toBeInTheDocument();

    // Verify prompts are rendered as hints
    expect(screen.getByText("First prompt")).toBeInTheDocument();
    expect(screen.getByText("Second prompt")).toBeInTheDocument();

    // Click Skip Challenge to unlock standard UI
    await user.click(screen.getByRole("button", { name: "Skip Challenge" }));

    // Verify it unlocks the standard recording UI
    expect(screen.queryByText("Arrange the Story Scenes")).not.toBeInTheDocument();
    expect(screen.getByText("Recording options")).toBeInTheDocument();
  });

  it("requires finishing the vocabulary quiz once before Practice Speaking unlocks, then remembers it's done", async () => {
    const user = userEvent.setup();

    const { unmount } = render(
      <StoryRecorder
        topic={topicWithQuizVocab}
        selectedImage={topicWithQuizVocab.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={vi.fn()}
        enableOverview={true}
      />,
    );

    // Lands on the choice screen first, not straight into practice.
    expect(screen.getByText("Your Challenge")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Vocabulary quiz" })).not.toBeInTheDocument();

    // Vocabulary is available (this topic has translated words), but
    // Speaking starts locked until the quiz has been completed once.
    const vocabChoice = screen.getByRole("button", { name: /Vocabulary Quiz/ });
    const speakingChoice = screen.getByRole("button", { name: /Speaking Practice/ });
    expect(vocabChoice).toBeEnabled();
    expect(speakingChoice).toBeDisabled();

    // Picking "Practice Vocabulary" goes to the quiz — never a skip button,
    // in any mode, whether or not it's been completed before.
    await user.click(vocabChoice);
    expect(screen.getByRole("region", { name: "Vocabulary quiz" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Skip/ })).not.toBeInTheDocument();

    // Backing out still leaves Speaking locked — only finishing unlocks it.
    await user.click(screen.getByRole("button", { name: /Back to activities/ }));
    expect(screen.getByRole("button", { name: /Speaking Practice/ })).toBeDisabled();

    // Finish the quiz for real this time. The overview section was
    // unmounted and remounted when we left and returned to it, so the
    // earlier `vocabChoice` reference is stale — query it fresh.
    await user.click(screen.getByRole("button", { name: /Vocabulary Quiz/ }));
    await completeVocabQuiz(user);

    // Landed in practice directly (quiz auto-advances on completion), with
    // the scene vocabulary table visible.
    expect(screen.getByRole("table", { name: "Scene vocabulary" })).toBeInTheDocument();

    // Simulate revisiting this story fresh: Speaking is now unlocked
    // (completion was persisted). Re-entering the quiz voluntarily still
    // has no skip button — "Back to activities" remains the only way out.
    unmount();
    render(
      <StoryRecorder
        topic={topicWithQuizVocab}
        selectedImage={topicWithQuizVocab.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={vi.fn()}
        enableOverview={true}
      />,
    );
    expect(screen.getByRole("button", { name: /Speaking Practice/ })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: /Vocabulary Quiz/ }));
    expect(screen.queryByRole("button", { name: /Skip/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Back to activities/ })).toBeInTheDocument();
  });

  it("disables the vocabulary quiz choice when a story has no translated words", () => {
    render(
      <StoryRecorder
        topic={topic}
        selectedImage={topic.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={vi.fn()}
        enableOverview={true}
      />,
    );

    expect(screen.getByRole("button", { name: /Vocabulary Quiz/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Speaking Practice/ })).toBeEnabled();
  });

  it("shows the scene vocabulary as a read-only table with pos/translation, no status before analysis", async () => {
    const user = userEvent.setup();
    render(
      <StoryRecorder
        topic={topicWithVocabDetails}
        selectedImage={topicWithVocabDetails.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={vi.fn()}
      />,
    );

    // This topic now has 1 translated word, enough to trigger the vocab
    // quiz gate — it's mandatory the first time, so answer through it to
    // reach practice, which is what this test actually covers.
    await completeVocabQuiz(user);

    const table = screen.getByRole("table", { name: "Scene vocabulary" });
    expect(within(table).getByText("market")).toBeInTheDocument();
    expect(within(table).getByText("shìchǎng")).toBeInTheDocument();
    expect(within(table).getByText("N")).toBeInTheDocument();
    expect(within(table).getByText("marketplace")).toBeInTheDocument();

    // "help" has no translation supplied — cell should just be empty, not crash.
    expect(within(table).getByText("help")).toBeInTheDocument();
    expect(within(table).getByText("bāngmáng")).toBeInTheDocument();
    expect(within(table).getByText("V")).toBeInTheDocument();

    // No recording analyzed yet: no used/missing status tint or tick.
    const rows = within(table).getAllByRole("row");
    for (const row of rows) {
      expect(row.className).not.toContain("scene-vocab-used");
      expect(row.className).not.toContain("scene-vocab-missed");
    }
  });

  it("shows the key vocabulary overview as a read-only table with pos/translation", () => {
    render(
      <StoryRecorder
        topic={topicWithVocabDetails}
        selectedImage={topicWithVocabDetails.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={vi.fn()}
        enableSorting={true}
        enableOverview={true}
      />,
    );

    const table = screen.getByRole("table", { name: "Key vocabulary" });
    expect(within(table).getByText("market")).toBeInTheDocument();
    expect(within(table).getByText("shìchǎng")).toBeInTheDocument();
    expect(within(table).getByText("N")).toBeInTheDocument();
    expect(within(table).getByText("marketplace")).toBeInTheDocument();
  });

  it("lets a student expand a scene vocabulary word to practice its pronunciation", async () => {
    const user = userEvent.setup();
    render(
      <StoryRecorder
        topic={topicWithVocabDetails}
        selectedImage={topicWithVocabDetails.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={vi.fn()}
      />,
    );

    // Finish the mandatory vocab quiz gate (this topic has 1 translated
    // word, enough to trigger it) to reach the practice-phase vocab table.
    await completeVocabQuiz(user);

    const practiceToggle = screen.getByRole("button", {
      name: "Practice pronouncing market",
    });

    // Collapsed by default — no per-word record control for this word yet.
    expect(
      screen.queryByRole("button", { name: "Record market to check pronunciation" }),
    ).not.toBeInTheDocument();

    await user.click(practiceToggle);
    expect(
      screen.getByRole("button", { name: "Record market to check pronunciation" }),
    ).toBeInTheDocument();

    // Toggling again collapses it.
    await user.click(
      screen.getByRole("button", { name: "Hide pronunciation practice for market" }),
    );
    expect(
      screen.queryByRole("button", { name: "Record market to check pronunciation" }),
    ).not.toBeInTheDocument();
  });

  it("shows a vocabulary quiz before practice when the story has enough translated words", async () => {
    const user = userEvent.setup();
    render(
      <StoryRecorder
        topic={topicWithQuizVocab}
        selectedImage={topicWithQuizVocab.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={vi.fn()}
      />,
    );

    expect(screen.getByRole("region", { name: "Vocabulary quiz" })).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Scene vocabulary" })).not.toBeInTheDocument();
    // Mandatory the first time through — no skip button yet.
    expect(screen.queryByRole("button", { name: /Skip/ })).not.toBeInTheDocument();

    await completeVocabQuiz(user);

    expect(screen.queryByRole("region", { name: "Vocabulary quiz" })).not.toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Scene vocabulary" })).toBeInTheDocument();
  });

  it("does not show the vocabulary quiz when a story has no translated words", () => {
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

    expect(screen.queryByRole("region", { name: "Vocabulary quiz" })).not.toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Scene vocabulary" })).toBeInTheDocument();
  });

  it("walks a scene through separate Vocabulary → Grammar → Speaking steps instead of showing everything at once", async () => {
    const user = userEvent.setup();
    const topicWithGrammar = {
      ...topicWithVocabDetails,
      grammarPatterns: { 0: "S + V + O" },
      grammarExamples: { 0: "我去市場。" },
    };

    render(
      <StoryRecorder
        topic={topicWithGrammar}
        selectedImage={topicWithGrammar.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={vi.fn()}
      />,
    );

    // Finish the mandatory vocab quiz gate (this topic has a translated
    // word, enough to trigger it) to reach the practice-phase Vocabulary step.
    await completeVocabQuiz(user);

    // Lands on Vocabulary by default — no record controls, grammar text, or
    // the story submit panel yet.
    expect(screen.getByRole("table", { name: "Scene vocabulary" })).toBeInTheDocument();
    expect(screen.queryByText("Recording options")).not.toBeInTheDocument();
    expect(screen.queryByText("S + V + O")).not.toBeInTheDocument();
    expect(screen.queryByText("Submit Story to Teacher")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Continue to Grammar/ }));

    // Grammar step: pattern shown, vocab table/record controls/submit panel gone.
    expect(screen.getByText("S + V + O")).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Scene vocabulary" })).not.toBeInTheDocument();
    expect(screen.queryByText("Recording options")).not.toBeInTheDocument();
    expect(screen.queryByText("Submit Story to Teacher")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Continue to Speaking/ }));

    // Speaking step: record controls and the submit panel are back, grammar/vocab panels are gone.
    expect(screen.getByText("Recording options")).toBeInTheDocument();
    expect(screen.getByText("Submit Story to Teacher")).toBeInTheDocument();
    expect(screen.queryByText("S + V + O")).not.toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Scene vocabulary" })).not.toBeInTheDocument();

    // The tab bar lets a student jump straight back to Vocabulary at any time.
    await user.click(screen.getByRole("tab", { name: /Vocabulary/ }));
    expect(screen.getByRole("table", { name: "Scene vocabulary" })).toBeInTheDocument();
    expect(screen.queryByText("Submit Story to Teacher")).not.toBeInTheDocument();
  });
});

