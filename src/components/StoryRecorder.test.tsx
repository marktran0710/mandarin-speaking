import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { UserEvent } from "@testing-library/user-event";
import { toPinyin } from "../utils/pinyin";
import StoryRecorder, {
  vocabTooltip,
  planDistractorGrowth,
  buildDistractorPatchUpdates,
  planClozeGrowth,
  buildClozePatchUpdates,
} from "./StoryRecorder";

// Every quiz-eligible word across this file's topic fixtures, with the data
// needed to answer any tier-1 question kind correctly — the vocab quiz now
// gates practice on actually passing tier 1 (14/20 right), so the helper
// below must genuinely know the answers rather than losing on purpose.
const QUIZ_ANSWERS: Record<string, { translation: string; pinyin?: string }> = {
  market: { translation: "marketplace", pinyin: "shìchǎng" },
  help: { translation: "to help" },
  friend: { translation: "friend" },
  餐廳: { translation: "restaurant" },
  吃: { translation: "to eat" },
};

/** Answers every question of the current tier run correctly via
 * QUIZ_ANSWERS — tiers 1-2 only ever ask translation / reverse / pinyin
 * questions for these fixtures (no AI cloze/synonym data, no jsdom speech
 * synthesis), each identified here by its options group's aria-label. */
async function passTierRun(user: UserEvent, questionCount: number) {
  for (let i = 0; i < questionCount; i += 1) {
    const optionsGroup = screen.getByRole("group", {
      name: /What does|How do you read|Which word means/,
    });
    const label = optionsGroup.getAttribute("aria-label")!;
    let correct: string;
    let match = label.match(/^What does (.+) mean\?$/);
    if (match) {
      correct = QUIZ_ANSWERS[match[1]].translation;
    } else if ((match = label.match(/^How do you read (.+)\?$/))) {
      correct = QUIZ_ANSWERS[match[1]]?.pinyin ?? toPinyin(match[1]);
    } else {
      const translation = label.match(/^Which word means (.+)\?$/)![1];
      correct = Object.keys(QUIZ_ANSWERS).find(
        (word) => QUIZ_ANSWERS[word].translation === translation,
      )!;
    }
    await user.click(
      within(optionsGroup)
        .getAllByRole("button")
        .find((b) => b.textContent === correct)!,
    );
    await user.click(screen.getByRole("button", { name: /Next question|See results/ }));
  }
}

/** Climbs the star ladder far enough to open practice (⭐⭐: pass tier 1,
 * then the tier-2 challenge straight off its summary), if the tier-select
 * screen is showing, then continues past the results screen. Required to
 * advance past a first-time (locked-practice) quiz. */
async function completeVocabQuiz(user: UserEvent) {
  const tierButton = screen.queryByRole("button", { name: /Tier 1/ });
  if (!tierButton) return;
  await user.click(tierButton);
  await passTierRun(user, 20);

  await user.click(await screen.findByRole("button", { name: /Challenge Tier 2/ }));
  await passTierRun(user, 22);

  const continueButton = await screen.findByRole("button", { name: /Continue to practice/ });
  await user.click(continueButton);
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

describe("planDistractorGrowth", () => {
  const baseTopic = {
    images: ["scene-1.jpg"],
    vocabulary: { 0: ["餐廳", "吃"] },
    vocabularyTranslation: { 0: ["restaurant", "to eat"] },
    suggestedAnswers: { 0: "我在餐廳吃飯。" },
  };

  it("includes words with no persisted distractors yet", () => {
    const candidates = planDistractorGrowth(baseTopic);
    expect(candidates).toEqual([
      {
        frameIndex: 0,
        wordIndex: 0,
        word: "餐廳",
        translation: "restaurant",
        context: "我在餐廳吃飯。",
        existing: [],
      },
      {
        frameIndex: 0,
        wordIndex: 1,
        word: "吃",
        translation: "to eat",
        context: "我在餐廳吃飯。",
        existing: [],
      },
    ]);
  });

  it("skips words that already reached the 8-distractor cap", () => {
    const candidates = planDistractorGrowth({
      ...baseTopic,
      vocabularyDistractors: {
        0: [["a", "b", "c", "d", "e", "f", "g", "h"], ["kitchen"]],
      },
    });
    expect(candidates.map((c) => c.word)).toEqual(["吃"]);
    expect(candidates[0].existing).toEqual(["kitchen"]);
  });

  it("returns an empty array once every word is at cap (signal to skip the AI call)", () => {
    const candidates = planDistractorGrowth({
      ...baseTopic,
      vocabularyDistractors: {
        0: [
          ["a", "b", "c", "d", "e", "f", "g", "h"],
          ["a", "b", "c", "d", "e", "f", "g", "h"],
        ],
      },
    });
    expect(candidates).toEqual([]);
  });

  it("skips words with no translation", () => {
    const candidates = planDistractorGrowth({
      ...baseTopic,
      vocabularyTranslation: { 0: ["restaurant", ""] },
    });
    expect(candidates.map((c) => c.word)).toEqual(["餐廳"]);
  });
});

describe("buildDistractorPatchUpdates", () => {
  const candidates = [
    { frameIndex: 0, wordIndex: 0, word: "餐廳", translation: "restaurant", existing: [] },
    { frameIndex: 0, wordIndex: 1, word: "吃", translation: "to eat", existing: ["kitchen"] },
  ];

  it("maps AI results back to frame/word indices by word text", () => {
    const updates = buildDistractorPatchUpdates(candidates, [
      { word: "餐廳", distractors: ["hotel", "cafe"] },
      { word: "吃", distractors: ["to drink"] },
    ]);
    expect(updates).toEqual([
      { frameIndex: 0, wordIndex: 0, distractors: ["hotel", "cafe"] },
      { frameIndex: 0, wordIndex: 1, distractors: ["to drink"] },
    ]);
  });

  it("drops candidates the AI returned nothing for", () => {
    const updates = buildDistractorPatchUpdates(candidates, [
      { word: "餐廳", distractors: ["hotel"] },
    ]);
    expect(updates).toEqual([{ frameIndex: 0, wordIndex: 0, distractors: ["hotel"] }]);
  });

  it("returns an empty array when the AI returned nothing for any candidate", () => {
    expect(buildDistractorPatchUpdates(candidates, [])).toEqual([]);
  });
});

describe("planClozeGrowth", () => {
  const baseTopic = {
    images: ["scene-1.jpg"],
    vocabulary: { 0: ["餐廳", "吃"] },
    vocabularyTranslation: { 0: ["restaurant", "to eat"] },
    suggestedAnswers: { 0: "我在餐廳吃飯。" },
  };

  it("includes words with no persisted cloze candidates yet", () => {
    const candidates = planClozeGrowth(baseTopic);
    expect(candidates).toEqual([
      {
        frameIndex: 0,
        wordIndex: 0,
        word: "餐廳",
        translation: "restaurant",
        context: "我在餐廳吃飯。",
        existing: [],
      },
      {
        frameIndex: 0,
        wordIndex: 1,
        word: "吃",
        translation: "to eat",
        context: "我在餐廳吃飯。",
        existing: [],
      },
    ]);
  });

  it("skips words that already reached the 4-candidate cap, passing existing sentences as the avoid list", () => {
    const candidates = planClozeGrowth({
      ...baseTopic,
      vocabularyCloze: {
        0: [
          [
            { sentence: "s1", distractors: ["a"] },
            { sentence: "s2", distractors: ["b"] },
            { sentence: "s3", distractors: ["c"] },
            { sentence: "s4", distractors: ["d"] },
          ],
          [{ sentence: "s5", distractors: ["e"] }],
        ],
      },
    });
    expect(candidates.map((c) => c.word)).toEqual(["吃"]);
    expect(candidates[0].existing).toEqual(["s5"]);
  });

  it("returns an empty array once every word is at cap (signal to skip the AI call)", () => {
    const fullPool = [
      { sentence: "s1", distractors: ["a"] },
      { sentence: "s2", distractors: ["b"] },
      { sentence: "s3", distractors: ["c"] },
      { sentence: "s4", distractors: ["d"] },
    ];
    const candidates = planClozeGrowth({
      ...baseTopic,
      vocabularyCloze: { 0: [fullPool, fullPool] },
    });
    expect(candidates).toEqual([]);
  });

  it("skips words with no translation", () => {
    const candidates = planClozeGrowth({
      ...baseTopic,
      vocabularyTranslation: { 0: ["restaurant", ""] },
    });
    expect(candidates.map((c) => c.word)).toEqual(["餐廳"]);
  });
});

describe("buildClozePatchUpdates", () => {
  const candidates = [
    { frameIndex: 0, wordIndex: 0, word: "餐廳", translation: "restaurant", existing: [] },
    { frameIndex: 0, wordIndex: 1, word: "吃", translation: "to eat", existing: ["s1"] },
  ];

  it("maps AI results back to frame/word indices by word text", () => {
    const updates = buildClozePatchUpdates(candidates, [
      { word: "餐廳", sentence: "我在餐廳吃飯。", distractors: ["教室", "公園"] },
      { word: "吃", sentence: "我要吃飯。", distractors: ["喝"] },
    ]);
    expect(updates).toEqual([
      {
        frameIndex: 0,
        wordIndex: 0,
        candidates: [{ sentence: "我在餐廳吃飯。", distractors: ["教室", "公園"] }],
      },
      {
        frameIndex: 0,
        wordIndex: 1,
        candidates: [{ sentence: "我要吃飯。", distractors: ["喝"] }],
      },
    ]);
  });

  it("drops candidates the AI returned nothing for", () => {
    const updates = buildClozePatchUpdates(candidates, [
      { word: "餐廳", sentence: "我在餐廳吃飯。", distractors: ["教室"] },
    ]);
    expect(updates).toEqual([
      {
        frameIndex: 0,
        wordIndex: 0,
        candidates: [{ sentence: "我在餐廳吃飯。", distractors: ["教室"] }],
      },
    ]);
  });

  it("returns an empty array when the AI returned nothing for any candidate", () => {
    expect(buildClozePatchUpdates(candidates, [])).toEqual([]);
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

  it("lets a student record their own attempt and receive word-level pronunciation feedback", async () => {
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

    // Scene 0 has vocabulary, so practice lands on the Vocabulary step first
    // — jump straight to Speaking via the tab bar.
    await user.click(screen.getByRole("tab", { name: /Speaking/ }));

    await user.click(screen.getByText("Recording options"));
    await user.selectOptions(screen.getByLabelText(/Speech source/), "vibevoice");
    await user.click(screen.getByRole("button", { name: /Record$/ }));
    expect(activeRecorder?.state).toBe("recording");

    await user.click(screen.getByRole("button", { name: /Stop Recording$/ }));

    // Analysis lands on the results screen; the per-word feedback shows
    // alongside the meaning/vocabulary feedback, with no click required.
    await waitFor(() => {
      expect(screen.getByText("Character-by-character prosody")).toBeInTheDocument();
    });
    expect(screen.getByText("Pitch rises clearly.")).toBeInTheDocument();

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

  it("defaults live recording to browser Traditional Chinese transcription", async () => {
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

    // Scene 0 has vocabulary, so practice lands on the Vocabulary step first
    // — jump straight to Speaking via the tab bar.
    await user.click(screen.getByRole("tab", { name: /Speaking/ }));

    expect(screen.getByLabelText(/Speech source/)).toHaveValue("webspeech");
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

    // Scene 0 has vocabulary, so practice lands on the Vocabulary step first
    // — jump straight to Speaking via the tab bar.
    await user.click(screen.getByRole("tab", { name: /Speaking/ }));
    // Uploading with the webspeech default falls back to Groq (webspeech
    // itself can't transcribe a file) — pick ctwhisper explicitly.
    await user.selectOptions(screen.getByLabelText(/Speech source/), "ctwhisper");

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
    // Mount also fires a GET to /api/ai-providers, so find the /api/analyze
    // call by URL rather than assuming it's the first fetch.
    const analyzeCall = vi
      .mocked(globalThis.fetch)
      .mock.calls.find(([url]) => String(url).includes("/api/analyze"));
    const requestBody = analyzeCall?.[1]?.body as FormData;
    expect(requestBody.get("transcription")).toBe("");
    expect(requestBody.get("asr_model")).toBe("ctwhisper");
    expect(await screen.findByText(/story-attempt\.wav/)).toBeInTheDocument();
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

    // Scene 0 has vocabulary, so practice lands on the Vocabulary step first
    // — jump straight to Speaking via the tab bar.
    await user.click(screen.getByRole("tab", { name: /Speaking/ }));

    await user.click(screen.getByText("Recording options"));
    await user.selectOptions(screen.getByLabelText(/Speech source/), "vibevoice");

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
    // Mount also fires a GET to /api/ai-providers, so find the /api/analyze
    // call by URL rather than assuming it's the first fetch.
    const analyzeCall = vi
      .mocked(globalThis.fetch)
      .mock.calls.find(([url]) => String(url).includes("/api/analyze"));
    const requestBody = analyzeCall?.[1]?.body as FormData;
    expect(requestBody.get("transcription")).toBe("");
    expect(requestBody.get("asr_model")).toBe("vibevoice");
    expect(await screen.findByText(/story-attempt\.wav/)).toBeInTheDocument();
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
    expect(screen.getByText("Put the Story in Order")).toBeInTheDocument();
    expect(screen.queryByText("Recording options")).not.toBeInTheDocument();

    // Verify prompts are rendered as hints
    expect(screen.getByText("First prompt")).toBeInTheDocument();
    expect(screen.getByText("Second prompt")).toBeInTheDocument();

    // Click Skip to unlock standard UI
    await user.click(screen.getByRole("button", { name: /Skip/ }));

    // Verify it unlocks the standard recording UI — scene 0 has vocabulary,
    // so practice lands on the Vocabulary step first, then jump to Speaking.
    expect(screen.queryByText("Put the Story in Order")).not.toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /Speaking/ }));
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

    // Backing out (via the completed "Overview" step in the phase nav)
    // still leaves Speaking locked — only finishing unlocks it.
    await user.click(screen.getByRole("button", { name: /Overview/ }));
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
    // has no skip button — the "Overview" phase-nav step remains the only
    // way out.
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
    expect(screen.getByRole("button", { name: /Overview/ })).toBeInTheDocument();
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

  it("walks a scene through a merged Study step (vocabulary + phrases together) then Speaking, instead of a separate tab per reference type", async () => {
    const user = userEvent.setup();
    const topicWithPhrases = {
      ...topicWithVocabDetails,
      phrases: { 0: ["我要去市場"] },
      phrasesTranslation: { 0: ["I'm going to the market"] },
    };

    render(
      <StoryRecorder
        topic={topicWithPhrases}
        selectedImage={topicWithPhrases.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={vi.fn()}
      />,
    );

    // Finish the mandatory vocab quiz gate (this topic has a translated
    // word, enough to trigger it) to reach the practice-phase Study step.
    await completeVocabQuiz(user);

    // Lands on Study by default — vocabulary and phrases show together, no
    // record controls yet.
    expect(screen.getByRole("table", { name: "Scene vocabulary" })).toBeInTheDocument();
    expect(screen.getByText("我要去市場")).toBeInTheDocument();
    expect(screen.queryByText("Recording options")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Continue to Speaking/ }));

    // Speaking step: record controls are back, the Study panels are gone.
    expect(screen.getByText("Recording options")).toBeInTheDocument();
    expect(screen.queryByText("我要去市場")).not.toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Scene vocabulary" })).not.toBeInTheDocument();

    // The tab bar lets a student jump straight back to Study at any time.
    await user.click(screen.getByRole("tab", { name: /Study/ }));
    expect(screen.getByRole("table", { name: "Scene vocabulary" })).toBeInTheDocument();
    expect(screen.getByText("我要去市場")).toBeInTheDocument();
  });

  it("shows the teacher's suggested-answer sentence during the Speaking step so students can read along", async () => {
    const user = userEvent.setup();
    const topicWithSuggestedAnswer = {
      ...topicWithVocabDetails,
      suggestedAnswers: { 0: "我在餐廳吃飯。" },
    };

    render(
      <StoryRecorder
        topic={topicWithSuggestedAnswer}
        selectedImage={topicWithSuggestedAnswer.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={vi.fn()}
      />,
    );

    await completeVocabQuiz(user);
    await user.click(screen.getByRole("tab", { name: /Speaking/ }));

    expect(screen.getByText("我在餐廳吃飯。")).toBeInTheDocument();
  });
});

