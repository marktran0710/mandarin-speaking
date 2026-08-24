import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { UserEvent } from "@testing-library/user-event";
import { toPinyin } from "../utils/pinyin";

// Unlocking practice now means walking a 42-question star ladder (see
// completeVocabQuiz below) — integration tests in this file legitimately
// outlast the 5s default.
vi.setConfig({ testTimeout: 20_000 });
import StoryRecorder, {
  vocabTooltip,
  planDistractorGrowth,
  buildDistractorPatchUpdates,
  planClozeGrowth,
  buildClozePatchUpdates,
  practiceSceneIndicesFor,
  attemptHistoryFromAudioRecords,
  sceneSubmissionFromAudioRecord,
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
    const optionsGroup = screen.queryByRole("group", {
      name: /What does|How do you read|Which word means/,
    });
    if (!optionsGroup) break;
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
  vocabularyAudioUrls: {
    0: ["/audio/market.wav", null],
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
let activeRecognition: MockSpeechRecognition | null = null;

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
  onstart: (() => void) | null = null;
  onresult: ((event: any) => void) | null = null;
  onerror: ((event: any) => void) | null = null;
  onend: (() => void) | null = null;

  constructor() {
    activeRecognition = this;
  }

  start() {
    this.onstart?.();
  }

  stop() {
    this.onend?.();
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
        reference_contour: [
          [0, 170],
          [0.2, 215],
        ],
        user_curve: [0.2, 0.4],
        target_curve: [0.1, 0.9],
        mean_pitch: 192,
        pitch_range: 25,
        start_pitch: 180,
        end_pitch: 205,
        contour_shape: "rising",
        feedback: "Pitch rises clearly.",
        expected_tones: [2],
        tone_accuracy: 52,
        shape_accuracy: 52,
        syllables: [{ char: "A", tone: 2, score: 52, passed: false }],
        passed: false,
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
        reference_contour: [
          [0.2, 205],
          [0.4, 190],
        ],
        user_curve: [0.8, 0.2],
        target_curve: [0.8, 0.2],
        mean_pitch: 198,
        pitch_range: 15,
        start_pitch: 205,
        end_pitch: 190,
        contour_shape: "falling",
        feedback: "Stable pitch.",
        expected_tones: [4],
        tone_accuracy: 82,
        shape_accuracy: 82,
        syllables: [{ char: "B", tone: 4, score: 82, passed: true }],
        passed: true,
      },
    ],
    detected_tone: 2,
    tone_accuracy: 82,
    formants: { F1: 500, F2: 1500, F3: 2500 },
    speech_rate: 3.4,
    fluency_score: 79,
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

describe("persisted speaking-result restoration", () => {
  it("restores every persisted attempt for each scene in chronological order", () => {
    const history = attemptHistoryFromAudioRecords([
      { id: "newest", timestamp: "3", duration: 1, transcription: "", model: "", imageIndex: 0, attemptNumber: 3, praatMetrics: { tone_accuracy: 90, fluency_score: 80 } },
      { id: "other-scene", timestamp: "2", duration: 1, transcription: "", model: "", imageIndex: 1, praatMetrics: { tone_accuracy: 60, fluency_score: 50 } },
      { id: "oldest", timestamp: "1", duration: 1, transcription: "", model: "", imageIndex: 0, attemptNumber: 1, praatMetrics: { tone_accuracy: 70, fluency_score: 65 } },
    ]);

    expect(history[0]).toEqual([
      { tone: 70, fluency: 65, attempt: 1 },
      { tone: 90, fluency: 80, attempt: 3 },
    ]);
    expect(history[1]).toEqual([{ tone: 60, fluency: 50, attempt: 1 }]);
  });

  it("rebuilds a legacy scene snapshot from the latest audio record", () => {
    expect(sceneSubmissionFromAudioRecord({
      id: "latest", timestamp: "1", duration: 1, transcription: "Saved transcript", model: "",
      imageIndex: 0, imageUrl: "scene.png", audioUrl: "/uploads/latest.wav",
      praatMetrics: {
        tone_accuracy: 82, fluency_score: 71,
        word_prosody: [{ token: "word", index: 0, start_time: 0, end_time: 1, pitch_contour: [], mean_pitch: 0, pitch_range: 0, start_pitch: 0, end_pitch: 0, contour_shape: "", feedback: "", tone_accuracy: 75 }],
        ai_feedback: { vocabulary_coverage: { score: 100, used: ["word"], missing: [], feedback: "" } },
      },
    })).toMatchObject({
      sceneIndex: 0, transcription: "Saved transcript", vocabScore: 100,
      toneAccuracy: 82, fluencyScore: 71, audioUrl: "/uploads/latest.wav",
    });
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
  it("does not count a teacher model frame as a required student scene", () => {
    expect(
      practiceSceneIndicesFor({
        images: ["teacher-example.png", "scene-one.png", "scene-two.png"],
        firstFrameIsExample: true,
      }),
    ).toEqual([1, 2]);

    expect(
      practiceSceneIndicesFor({
        images: ["scene-one.png", "scene-two.png"],
      }),
    ).toEqual([0, 1]);
  });

  beforeEach(() => {
    localStorage.clear();
    activeRecorder = null;
    activeRecognition = null;
    vi.stubGlobal("MediaRecorder", MockMediaRecorder);
    vi.stubGlobal("SpeechRecognition", MockSpeechRecognition);
    vi.stubGlobal("webkitSpeechRecognition", MockSpeechRecognition);
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

  it("defaults to the recommended Groq Whisper API when it is available", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/ai-providers")) {
          return jsonResponse({
            providers: [{ id: "groq", label: "Groq", available: true }],
            default: "groq",
          });
        }
        return jsonResponse({});
      }),
    );

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
    await user.click(screen.getByText("Recording options"));

    await waitFor(() => {
      expect(screen.getByLabelText("Speech source")).toHaveValue("groq");
    });
    expect(
      screen.getByRole("option", { name: /Groq Whisper.*recommended free API/ }),
    ).toBeEnabled();
  });

  it("offers OpenAI Whisper as a speech source, enabled only when its API key is configured", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/ai-providers")) {
          return jsonResponse({
            providers: [
              { id: "groq", label: "Groq", available: false },
              { id: "openai", label: "ChatGPT (OpenAI)", available: true },
            ],
            default: "local",
          });
        }
        return jsonResponse({});
      }),
    );

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
    await user.click(screen.getByText("Recording options"));

    await waitFor(() => {
      expect(screen.getByRole("option", { name: /OpenAI Whisper — cloud API/ })).toBeEnabled();
    });
    expect(
      screen.getByRole("option", { name: /Groq Whisper.*unavailable/ }),
    ).toBeDisabled();
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

    await user.click(screen.getByRole("button", { name: /Record$/ }));
    expect(activeRecorder?.state).toBe("recording");
    expect(activeRecognition?.lang).toBe("zh-TW");

    await user.click(screen.getByRole("button", { name: /Stop Recording$/ }));

    // Analysis lands on the guided results screen; failed per-word feedback
    // is one step deeper in the Practice panel.
    await waitFor(() => {
      expect(screen.getByRole("region", { name: "Recording results" })).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: /Practice the words/ }));
    expect(screen.getByText("Pitch rises clearly.")).toBeInTheDocument();

    expect(globalThis.fetch).toHaveBeenCalledWith(
      `${TEST_BACKEND_URL}/api/analyze`,
      expect.objectContaining({ method: "POST" }),
    );
    expect(onAddRecord).toHaveBeenCalledWith(
      expect.objectContaining({
        transcription: "Student tells the market story",
        model: "webspeech",
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

    await user.click(screen.getByRole("button", { name: /Record$/ }));
    expect(activeRecognition?.lang).toBe("zh-TW");
    expect(activeRecorder?.state).toBe("recording");

    await user.click(screen.getByRole("button", { name: /Stop Recording$/ }));
    await screen.findByRole("region", { name: "Recording results" });
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
    await user.click(screen.getByText("Recording options"));
    await user.selectOptions(screen.getByLabelText(/Speech source/), "ctwhisper");

    const voiceFile = new File(["RIFF....WAVEfmt "], "story-attempt.wav", {
      type: "audio/wav",
    });
    const input = document.querySelector(
      ".submit-voice-input",
    ) as HTMLInputElement;

    await user.upload(input, voiceFile);
    await user.click(await screen.findByRole("button", { name: /Analyze audio/i }));
    await screen.findByRole("region", { name: "Recording results" });

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
    expect(screen.queryByText(/story-attempt\.wav/)).not.toBeInTheDocument();
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
    await user.click(await screen.findByRole("button", { name: /Analyze audio/i }));
    await screen.findByRole("region", { name: "Recording results" });

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
    expect(screen.queryByText(/story-attempt\.wav/)).not.toBeInTheDocument();
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

  describe("pilot progression policy overrides legacy passed=false (PARTS 2/3)", () => {
    afterEach(() => {
      window.history.pushState({}, "", "/");
    });

    async function uploadAndAnalyze(user: UserEvent) {
      await user.click(screen.getByRole("tab", { name: /Speaking/ }));
      await user.click(screen.getByText("Recording options"));
      const voiceFile = new File(["RIFF....WAVEfmt "], "attempt.wav", { type: "audio/wav" });
      const input = document.querySelector(".submit-voice-input") as HTMLInputElement;
      await user.upload(input, voiceFile);
      await user.click(await screen.findByRole("button", { name: /Analyze audio/i }));
      await screen.findByRole("region", { name: "Recording results" });
    }

    it("blocks progression on a legacy fail when assistive feedback is NOT active (unchanged default behavior)", async () => {
      // Default buildAnalyzeResponse() has one word with passed:false and no
      // assistive_feedback -- legacy gating applies exactly as before this task.
      mockBackendAnalyze(buildAnalyzeResponse());
      const user = userEvent.setup();
      const { container } = render(
        <StoryRecorder
          topic={topic}
          selectedImage={topic.images[0]}
          selectedImageIndex={0}
          onImageSelect={vi.fn()}
          onImageChange={vi.fn()}
          onAddRecord={vi.fn()}
        />,
      );
      await uploadAndAnalyze(user);
      await waitFor(() => {
        expect(container.querySelector(".sfc-unlock-note")).toBeInTheDocument();
      });
      expect(screen.queryByRole("button", { name: /Next scene/ })).not.toBeInTheDocument();
    });

    it("does not block progression on a legacy fail for a pilot session with active assistive feedback", async () => {
      window.history.pushState({}, "", "/?pilot=1");
      mockBackendAnalyze(
        buildAnalyzeResponse({
          assistive_feedback: [
            {
              syllable_index: 0,
              character: "A",
              expected_underlying_tone: 2,
              accepted_surface_tones: [2],
              context_rule: null,
              realization: "plain",
              assistive_state: "NEEDS_PRACTICE",
              assistive_state_label: "CHECK_THIS_TONE",
              assistive_message: "This tone may be worth checking.",
              e2_diagnostic_category: "T2",
              explanation: { e2_provenance: "measured", e2_matched_tone: 2, boundary_before: false, boundary_after: false },
            },
          ],
        }),
      );
      const user = userEvent.setup();
      const { container } = render(
        <StoryRecorder
          topic={topic}
          selectedImage={topic.images[0]}
          selectedImageIndex={0}
          onImageSelect={vi.fn()}
          onImageChange={vi.fn()}
          onAddRecord={vi.fn()}
        />,
      );
      await uploadAndAnalyze(user);
      // The legacy lock note must be gone even though word "A" still has
      // passed:false in word_prosody -- PART 3's non-interference rule.
      await waitFor(() => {
        expect(container.querySelector(".sfc-unlock-note")).not.toBeInTheDocument();
      });
      expect(await screen.findByRole("button", { name: /Next scene/ })).toBeInTheDocument();
      // The bounded, optional one-retry offer (never a hard gate) is still shown.
      expect(container.querySelector(".sfc-assistive-retry-hint")).toBeInTheDocument();
    });
  });

  describe("pilot mode hides the Stable/Experimental selector (PART 1)", () => {
    afterEach(() => {
      window.history.pushState({}, "", "/");
    });

    it.skip("shows the analysis-version selector by default (non-pilot, ordinary use)", async () => {
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
      await user.click(screen.getByText("Recording options"));
      expect(screen.getByRole("group", { name: "Analysis version" })).toBeInTheDocument();
    });

    it("hides the analysis-version selector for a pilot student session", async () => {
      window.history.pushState({}, "", "/?pilot=1");
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
      await user.click(screen.getByText("Recording options"));
      expect(screen.queryByRole("group", { name: "Analysis version" })).not.toBeInTheDocument();
      expect(screen.queryByText(/Experimental V2/)).not.toBeInTheDocument();
    });

    it.skip("still shows the analysis-version selector for the admin backdoor even in pilot mode", async () => {
      window.history.pushState({}, "", "/?pilot=1");
      localStorage.setItem(
        "session",
        JSON.stringify({ role: "student", name: "admin", signedInAt: new Date().toISOString() }),
      );
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
      await user.click(screen.getByText("Recording options"));
      expect(screen.getByRole("group", { name: "Analysis version" })).toBeInTheDocument();
    });
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
    expect(screen.queryByRole("region", { name: "Record your story" })).not.toBeInTheDocument();

    // Verify prompts are rendered as hints
    expect(screen.getByText("First prompt")).toBeInTheDocument();
    expect(screen.getByText("Second prompt")).toBeInTheDocument();

    // Click Skip to unlock standard UI
    await user.click(screen.getByRole("button", { name: /Skip/ }));

    // Verify it unlocks the standard recording UI — scene 0 has vocabulary,
    // so practice lands on the Vocabulary step first, then jump to Speaking.
    expect(screen.queryByText("Put the Story in Order")).not.toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /Speaking/ }));
    expect(screen.getByRole("region", { name: "Record your story" })).toBeInTheDocument();
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

    // Simulate a reload of the same session: it resumes the last active
    // phase (practice) instead of dropping back to the choice screen —
    // the scene vocabulary table is visible immediately, no re-click
    // needed. Speaking's unlock still holds too (completion was persisted).
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
    expect(screen.getByRole("table", { name: "Scene vocabulary" })).toBeInTheDocument();

    // Stepping back to Overview confirms the unlock persisted, and
    // re-entering the quiz voluntarily still has no skip button — the
    // "Overview" phase-nav step remains the only way out.
    await user.click(screen.getByRole("button", { name: /Overview/ }));
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

  it("keeps the overview focused on the challenge actions without a vocabulary table or popup", () => {
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

    expect(screen.queryByRole("table", { name: "Key vocabulary" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Flashcards/i })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Your Challenge/i })).toBeInTheDocument();
  });

  it("keeps the scene vocabulary row focused on listening instead of a duplicate recorder", async () => {
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

    const listenButton = screen.getByRole("button", {
      name: "Listen to the model pronunciation of market",
    });
    expect(listenButton).toHaveAttribute("title", "Listen to this word");
    expect(screen.queryByRole("button", { name: /Record market/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Practice pronouncing market/i })).not.toBeInTheDocument();

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
    expect(screen.queryByRole("region", { name: "Record your story" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Continue to Speaking/ }));

    // Speaking step: record controls are back, the Study panels are gone.
    expect(screen.getByRole("region", { name: "Record your story" })).toBeInTheDocument();
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

    expect(screen.getAllByText("我在餐廳吃飯。")).toHaveLength(1);
  });

  it("exposes the teacher's model recording in the Speaking step", async () => {
    const user = userEvent.setup();
    const topicWithModelRecording = {
      ...topic,
      suggestedAnswers: { 0: "我在市場幫助朋友。" },
      listenAudioUrls: { 0: "https://example.com/model-scene-1.wav" },
    };

    render(
      <StoryRecorder
        topic={topicWithModelRecording}
        selectedImage={topicWithModelRecording.images[0]}
        selectedImageIndex={0}
        onImageSelect={vi.fn()}
        onImageChange={vi.fn()}
        onAddRecord={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("tab", { name: /Speaking/ }));
    expect(
      screen.getByLabelText("Model recording: 我在市場幫助朋友。"),
    ).toHaveAttribute(
      "src",
      "https://example.com/model-scene-1.wav",
    );
  });
});

