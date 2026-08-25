import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { UserEvent } from "@testing-library/user-event";
import { toPinyin } from "../utils/pinyin";

// Unlocking practice now means walking a 67-question star ladder (see
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
const QUIZ_ANSWERS: Record<string, { translation: string; pinyin?: string; pos?: string }> = {
  market: { translation: "marketplace", pinyin: "shìchǎng", pos: "N" },
  help: { translation: "to help", pos: "V" },
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
      name: /What does|What part of speech|How do you read|Which word means/,
    });
    if (!optionsGroup) break;
    const label = optionsGroup.getAttribute("aria-label")!;
    let correct: string;
    let match = label.match(/^What does (.+) mean\?$/);
    if (match) {
      correct = QUIZ_ANSWERS[match[1]].translation;
    } else if ((match = label.match(/^How do you read (.+)\?$/))) {
      correct = QUIZ_ANSWERS[match[1]]?.pinyin ?? toPinyin(match[1]);
    } else if ((match = label.match(/^What part of speech is (.+)\?$/))) {
      correct = QUIZ_ANSWERS[match[1]]?.pos!;
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

/** Climbs the complete ladder (⭐⭐⭐: pass tiers 1, 2, then 3), if the
 * tier-select screen is showing, then continues past the results screen.
 * Required to advance past a first-time locked-practice quiz. */
async function completeVocabQuiz(user: UserEvent) {
  const tierButton = screen.queryByRole("button", { name: /Tier 1/ });
  if (!tierButton) return;
  await user.click(tierButton);
  await passTierRun(user, 20);

  await user.click(await screen.findByRole("button", { name: /Challenge Tier 2/ }));
  await passTierRun(user, 22);

  await user.click(await screen.findByRole("button", { name: /Challenge Tier 3/ }));
  await passTierRun(user, 25);

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
export function resetStoryRecorderTestEnvironment() {
  localStorage.clear();
  activeRecorder = null;
  activeRecognition = null;
  vi.stubGlobal("MediaRecorder", MockMediaRecorder);
  vi.stubGlobal("SpeechRecognition", MockSpeechRecognition);
  vi.stubGlobal("webkitSpeechRecognition", MockSpeechRecognition);
  mockBackendAnalyze(buildAnalyzeResponse());
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia: vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn() }] })) },
  });
}

export function cleanupStoryRecorderTestEnvironment() {
  vi.unstubAllGlobals();
}

export {
  QUIZ_ANSWERS,
  passTierRun,
  completeVocabQuiz,
  topic,
  topicWithVocabDetails,
  topicWithQuizVocab,
  TEST_BACKEND_URL,
  activeRecorder,
  activeRecognition,
  MockMediaRecorder,
  MockSpeechRecognition,
  jsonResponse,
  buildAnalyzeResponse,
  mockBackendAnalyze,
};
