import type { AudioRecord } from "../pages/MyStoriesPage";

export type DebugAttemptSource = "runtime" | "recorded" | "sample";

const SENSITIVE_KEY = /(^|_)(api_?key|authorization|cookie|password|secret|token|credential|signature)($|_)/i;
const BINARY_KEY = /(audio_?blob|audio_?bytes|image_?b64|base64|file)/i;

function redactUrl(value: string): string {
  if (!/^https?:\/\//i.test(value)) return value;
  try {
    const url = new URL(value);
    for (const key of [...url.searchParams.keys()]) {
      if (SENSITIVE_KEY.test(key) || /^(key|sig|x-amz-)/i.test(key)) {
        url.searchParams.set(key, "[REDACTED]");
      }
    }
    return url.toString();
  } catch {
    return value;
  }
}

/** Removes credentials and large binary bodies before a payload reaches the UI. */
export function redactDebugValue(value: unknown, key = ""): unknown {
  if (SENSITIVE_KEY.test(key)) return "[REDACTED]";
  if (BINARY_KEY.test(key) && value != null) return "[binary omitted]";
  if (typeof value === "string") {
    if (/^data:(audio|image)\//i.test(value)) return "[binary data URL omitted]";
    return redactUrl(value);
  }
  if (Array.isArray(value)) return value.map((item) => redactDebugValue(item));
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([childKey, childValue]) => [
        childKey,
        redactDebugValue(childValue, childKey),
      ]),
    );
  }
  return value;
}

export const SAMPLE_DEBUG_RECORD: AudioRecord = {
  id: "sample-practice-attempt",
  timestamp: "Sample data (not saved)",
  duration: 5.8,
  transcription: "小明在公園裡騎腳踏車。",
  model: "sample-asr",
  topicId: "sample-story",
  imageIndex: 1,
  praatMetrics: {
    transcription: "小明在公園裡騎腳踏車。",
    transcription_model: "sample-asr",
    pitch_contour: [[0.1, 184], [0.3, 196], [0.5, 178]],
    detected_tone: 3,
    tone_accuracy: 76,
    formants: { F1: 510, F2: 1480, F3: 2510 },
    vowel_quality: "Vowel spacing is within the expected practice range.",
    speech_rate: 3.1,
    fluency_score: 72,
    pitch_statistics: { mean_frequency: 186, frequency_range: 42 },
    pause_analysis: {
      duration: 5.8, utterance_count: 1, pause_count: 1,
      total_pause_duration: 0.35, longest_pause: 0.35, speech_ratio: 0.79,
      articulation_rate: 3.9, choppy_pause_count: 0, natural_pause_count: 1,
    },
    word_prosody: [
      {
        token: "小明", expected_tones: [3, 2], tone_accuracy: 81,
        shape_accuracy: 79, judged: true, passed: true,
        syllables: [
          { char: "小", tone: 3, score: 77, passed: true },
          { char: "明", tone: 2, score: 84, passed: true },
        ],
      },
      {
        token: "公園", expected_tones: [1, 2], tone_accuracy: 55,
        shape_accuracy: 59, judged: true, passed: false,
        syllables: [
          { char: "公", tone: 1, score: 63, passed: true },
          { char: "園", tone: 2, score: 47, passed: false },
        ],
      },
    ],
    feedback: "The second tone in 公園 needs a clearer rise.",
    feedback_quality: {
      status: "ok", can_score_pronunciation: true, can_score_content: true,
      student_message: "",
    },
    ai_feedback: {
      provider: "local",
      vocabulary_coverage: {
        score: 67, used: ["公園", "騎"], missing: ["安全帽"],
        feedback: "Used 2/3 scene words.",
      },
      coherence: { score: 58, feedback: "Add a connective to extend the idea.", corrections: [] },
      pronunciation_note: {
        score: 65,
        feedback: "Tone-contour match 76%; keep working on the weaker tones.",
      },
      content_accuracy: {
        score: 82, feedback: "The sentence matches the main action in the scene.",
        matched_details: ["person", "park", "cycling"], missed_details: ["helmet"],
        accepted: true, judged: true,
      },
      improved_version: "小明戴著安全帽，在公園裡騎腳踏車。",
      practice_prompt: "Say it again and add 安全帽.",
    },
    processing_trace: {
      total_duration_ms: 1840,
      stages: [
        {
          stage: "preflight", status: "reliable", duration_ms: 18,
          detail: "Sound check passed.", reason_codes: [],
          input: { audio_bytes: 92_000 },
          output: { status: "reliable", confidence: 0.95, can_score_pronunciation: true, can_score_content: true },
        },
        {
          stage: "asr", status: "passed", duration_ms: 640, model: "sample-asr",
          detail: "Backend transcription completed.",
          input: { asr_model: "sample-asr", scene_vocabulary: "公園, 騎腳踏車, 安全帽" },
          output: { transcription: "小明在公園裡騎腳踏車。", model: "sample-asr" },
        },
        {
          stage: "praat", status: "passed", duration_ms: 210, detail: "Acoustic analysis completed.",
          input: { pinyin_hint: null, reference_word_curves_provided: false },
          output: {
            pitch_contour: [[0.1, 184], [0.3, 196], [0.5, 178]],
            formants: { F1: 510, F2: 1480, F3: 2510 },
            speech_rate: 3.1, fluency_score: 72,
            pitch_statistics: { mean_frequency: 186, frequency_range: 42 },
            detected_tone: 3, tone_accuracy: 76,
          },
        },
        {
          stage: "feedback", status: "passed", duration_ms: 960, provider: "local",
          detail: "Provider feedback completed.",
          input: { scene_prompt: "A boy rides a bicycle in the park.", scene_vocabulary: "公園, 騎腳踏車, 安全帽", scene_attempt_number: 1, image_provided: false },
          output: {
            provider: "local",
            vocabulary_coverage: { score: 67, used: ["公園", "騎"], missing: ["安全帽"] },
            coherence: { score: 58 },
            content_accuracy: { score: 82, accepted: true, judged: true },
          },
        },
        {
          stage: "quality_gate", status: "passed", duration_ms: 12, detail: "Quality gate evaluated.",
          input: { preflight_status: "reliable", content_was_verified: false },
          output: { status: "ok", can_score_pronunciation: true, can_score_content: true, student_message: "" },
        },
      ],
    },
  },
};
