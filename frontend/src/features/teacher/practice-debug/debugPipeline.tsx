import { type ReactNode } from "react";
import type { AudioRecord } from "@entities/audio";
import type { SpeechModel } from "../../../components/story-recorder/StoryRecorder";
import { redactDebugValue, type DebugAttemptSource } from "../../../utils/practiceDebug";

export type JsonObject = Record<string, any>;

export const RUBRICS = [
  {
    name: "Recording quality gate",
    owner: "Backend preflight",
    rule: "Silence / unusable audio disables pronunciation scoring; tone and fluency are returned as 0, not as a learner judgement.",
  },
  {
    name: "Tone contour",
    owner: "Praat + tone matcher",
    rule: "Per-word scores are weighted by expected syllable count. Every syllable must score ≥58 for that word to pass.",
  },
  {
    name: "Fluency",
    owner: "Praat + CAF",
    rule: "65% utterance fluency + 35% pitch continuity. Utterance fluency = 40% phonation ratio + 35% articulation rate + 25% mean run length.",
  },
  {
    name: "Vocabulary coverage",
    owner: "Local matcher / AI",
    rule: "When target words exist: matched target words ÷ target words. Local matching accepts characters or a pinyin homophone.",
  },
  {
    name: "Coherence (local fallback)",
    owner: "CAF text metrics",
    rule: "70% utterance-length score + 30% connective-density score. Cloud feedback uses the same response schema but is model-judged.",
  },
  {
    name: "Pronunciation coaching note (local)",
    owner: "Praat-grounded fallback",
    rule: "88 when tone ≥80 and fluency ≥75; otherwise 65 when tone ≥60, 45 when tone is 1–59, or 50 as an unscored practice prompt when no tone evidence exists.",
  },
  {
    name: "Scene content",
    owner: "Vision-capable AI",
    rule: "Accepted at ≥60. If no image-capable judge ran, judged=false and this must not be treated as a failing score.",
  },
];

export function sourceLabel(source: DebugAttemptSource) {
  if (source === "runtime") return "Runtime record";
  if (source === "recorded") return "Live debug recording";
  return "Transparent sample";
}

export interface RecordedRequestContext {
  scenePrompt: string;
  sceneVocabulary: string;
  sceneImageUrl: string;
  scenePhrases: string;
  sceneSuggestedAnswer: string;
  sceneReferenceCurves: Record<string, number[]> | null;
  asrModel: SpeechModel;
}

export type DebugProcessingState = "idle" | "recording" | "uploading" | "processing" | "complete" | "error";
export type DebugTraceStatus = "pending" | "running" | "passed" | "integrated" | "review" | "retry" | "skipped" | "failed";
export type AnalysisPhase = "idle" | "preparing" | "backend";

export const AUDIO_PREPARATION_TIMEOUT_MS = 30_000;
export const BACKEND_ANALYSIS_TIMEOUT_MS = 120_000;

export async function withTimeout<T>(promise: Promise<T>, timeoutMs: number, message: string): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      promise,
      new Promise<T>((_, reject) => {
        timer = setTimeout(() => reject(new Error(message)), timeoutMs);
      }),
    ]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}

export interface ProcessingTraceStage {
  stage: string;
  status: DebugTraceStatus | string;
  duration_ms?: number;
  model?: string | null;
  provider?: string | null;
  detail?: string | null;
  reason_codes?: string[];
  input?: JsonObject | null;
  output?: JsonObject | null;
}

export interface StageDefinition {
  id: string;
  label: string;
  description: string;
}

// One canonical pipeline that drives both the trace timeline and the
// per-step input/output cards below it — these ids match the backend's
// `add_trace_stage` calls exactly, so the two views can never drift apart.
export const TRACE_STAGE_DEFINITIONS: StageDefinition[] = [
  { id: "capture", label: "Record", description: "Microphone input" },
  { id: "preflight", label: "Preflight", description: "Audio quality gate" },
  { id: "asr", label: "ASR", description: "Transcript" },
  { id: "praat", label: "Praat", description: "Acoustic analysis" },
  { id: "feedback", label: "Feedback", description: "AI / local CAF" },
  { id: "quality_gate", label: "Decision", description: "Student next step" },
];

export function traceStatusLabel(status: string) {
  if (status === "passed" || status === "integrated" || status === "reliable") return "Complete";
  if (status === "retry" || status === "failed") return status === "retry" ? "Retry" : "Failed";
  if (status === "review") return "Review";
  if (status === "skipped") return "Skipped";
  if (status === "running") return "Running";
  return "Waiting";
}

export function traceDurationLabel(durationMs?: number) {
  if (typeof durationMs !== "number" || !Number.isFinite(durationMs)) return "";
  return durationMs < 1000 ? `${Math.round(durationMs)} ms` : `${(durationMs / 1000).toFixed(1)} s`;
}

export function JsonPanel({ value, label }: { value: unknown; label: string }) {
  return (
    <details className="pdebug-json">
      <summary>{label}</summary>
      <pre>{JSON.stringify(redactDebugValue(value), null, 2)}</pre>
    </details>
  );
}

export function metric(value: unknown, suffix = "") {
  return typeof value === "number" && Number.isFinite(value)
    ? `${Math.round(value)}${suffix}`
    : "Not available";
}

/** Reads the /api/analyze/stream response line by line and reports each
 * completed stage the moment it arrives, instead of waiting for the whole
 * analysis to finish. Falls back to a single JSON read if the runtime
 * doesn't expose a readable stream body (older browsers, some test doubles). */
export async function consumeAnalysisStream(
  response: Response,
  onStage: (stage: ProcessingTraceStage) => void,
): Promise<JsonObject> {
  const reader = response.body?.getReader();
  if (!reader) return response.json();

  const decoder = new TextDecoder();
  let buffer = "";
  let result: JsonObject | null = null;
  let streamError: string | null = null;

  for (;;) {
    const { value, done } = await reader.read();
    if (value) buffer += decoder.decode(value, { stream: true });
    let separatorIndex: number;
    while ((separatorIndex = buffer.indexOf("\n\n")) !== -1) {
      const rawEvent = buffer.slice(0, separatorIndex);
      buffer = buffer.slice(separatorIndex + 2);
      const dataLine = rawEvent.split("\n").find((line) => line.startsWith("data:"));
      if (!dataLine) continue;
      const payload = JSON.parse(dataLine.slice(5).trim());
      if (payload.type === "stage") {
        const { type: _type, ...stage } = payload;
        onStage(stage as ProcessingTraceStage);
      } else if (payload.type === "result") {
        result = payload.result;
      } else if (payload.type === "error") {
        streamError = payload.detail;
      }
    }
    if (done) break;
  }

  if (streamError) throw new Error(streamError);
  if (!result) throw new Error("Analysis stream ended without a result.");
  return result;
}

export function stageDlContent(
  id: string,
  entry: ProcessingTraceStage | undefined,
  ctx: {
    record: AudioRecord;
    praat: JsonObject;
    ai: JsonObject;
    words: JsonObject[];
    contentGate: string;
    canScorePronunciation: boolean;
  },
): Array<[string, string]> {
  switch (id) {
    case "capture":
      return [
        ["Record ID", ctx.record.id],
        ["Topic / scene", `${ctx.record.topicId || "Not persisted"} / ${ctx.record.imageIndex ?? "—"}`],
        ["Audio duration", ctx.record.duration ? `${ctx.record.duration}s` : "Not available"],
      ];
    case "preflight":
      return [
        ["Status", entry?.output?.status ?? "Not available"],
        ["Reason codes", (entry?.reason_codes ?? []).join(", ") || "None"],
      ];
    case "asr":
      return [
        ["Model", entry?.output?.model || ctx.praat.transcription_model || "Not available"],
        ["Transcript", entry?.output?.transcription || ctx.praat.transcription || "No transcript"],
      ];
    case "praat":
      return [
        ["Speech rate", typeof ctx.praat.speech_rate === "number" ? `${ctx.praat.speech_rate.toFixed(2)} syl/s` : "Not available"],
        ["Words judged", String(ctx.words.length)],
      ];
    case "feedback":
      return [
        ["Provider", entry?.provider || ctx.ai.provider || "Not available"],
        [
          "Vocabulary score",
          typeof ctx.ai.vocabulary_coverage?.score === "number"
            ? `${Math.round(ctx.ai.vocabulary_coverage.score)}/100`
            : "Not available",
        ],
      ];
    case "content_verification":
      return [
        ["Word", entry?.input?.verify_word ?? "Not available"],
        [
          "Match",
          entry?.output?.content_match === true
            ? "Yes"
            : entry?.output?.content_match === false
              ? "No"
              : "Not checked",
        ],
      ];
    case "quality_gate":
      return [
        ["Pronunciation scoreable", ctx.canScorePronunciation ? "Yes" : "No"],
        ["Scene meaning", ctx.contentGate],
      ];
    default:
      return [];
  }
}

export interface PipelineViewInputs {
  record: AudioRecord;
  source: DebugAttemptSource;
  processingState: DebugProcessingState;
  processingTrace: ProcessingTraceStage[];
  isRecording: boolean;
  inputSource: "microphone" | "upload";
  uploadedAudioName: string;
  recordedAudioUrl: string;
  recordingDuration: number;
  recordingError: string;
}

export interface PipelineView {
  praat: JsonObject;
  ai: JsonObject;
  words: JsonObject[];
  failedWords: JsonObject[];
  canScorePronunciation: boolean;
  contentGate: string;
  activeTrace: ProcessingTraceStage[];
  outputReady: boolean;
  statusForStage: (stageId: string) => ProcessingTraceStage;
  stageDefinitions: StageDefinition[];
  captureEntry: ProcessingTraceStage;
}

/** Turns one analysis result (live or stored) into everything `DebugPipelineDetails`
 * needs to render it — shared by the single-attempt Practice Debugger and the
 * side-by-side ASR Compare tool so both read the exact same pipeline shape. */
export function derivePipelineView(inputs: PipelineViewInputs): PipelineView {
  const {
    record, source, processingState, processingTrace, isRecording,
    inputSource, uploadedAudioName, recordedAudioUrl, recordingDuration, recordingError,
  } = inputs;
  const praat = (record.praatMetrics ?? {}) as JsonObject;
  const ai = (praat.ai_feedback ?? {}) as JsonObject;
  const quality = (praat.feedback_quality ?? {}) as JsonObject;
  const words = Array.isArray(praat.word_prosody) ? praat.word_prosody : [];
  const failedWords = words.filter((word: JsonObject) => word.judged === false || word.passed === false);
  const canScorePronunciation = quality.can_score_pronunciation !== false;
  const content = (ai.content_accuracy ?? {}) as JsonObject;
  const contentGate = quality.can_score_content === false
    ? "Not scoreable"
    : content.judged === false || content.judged == null
      ? "Not judged"
      : content.accepted
        ? "Passed"
        : "Needs retry";
  const storedTrace = Array.isArray((praat.processing_trace as JsonObject | undefined)?.stages)
    ? (praat.processing_trace as JsonObject).stages as ProcessingTraceStage[]
    : [];
  const activeTrace = processingState !== "idle" ? processingTrace : storedTrace;
  const traceByStage = new Map(activeTrace.map((entry) => [entry.stage, entry]));
  const outputReady = processingState === "idle" || processingState === "complete";
  const statusForStage = (stageId: string): ProcessingTraceStage => {
    const existing = traceByStage.get(stageId);
    if (existing) return existing;
    if (stageId === "capture") {
      return { stage: stageId, status: processingState === "recording" ? "running" : "passed" };
    }
    if (processingState === "uploading" && stageId === "preflight") return { stage: stageId, status: "running" };
    if (processingState === "processing" && stageId === "preflight") return { stage: stageId, status: "running" };
    if (processingState === "error" && stageId === "quality_gate") return { stage: stageId, status: "failed", detail: recordingError };
    return { stage: stageId, status: "pending" };
  };
  const hasVerificationStage = activeTrace.some((entry) => entry.stage === "content_verification");
  const stageDefinitions: StageDefinition[] = !hasVerificationStage
    ? TRACE_STAGE_DEFINITIONS
    : (() => {
        const gateIndex = TRACE_STAGE_DEFINITIONS.findIndex((definition) => definition.id === "quality_gate");
        return [
          ...TRACE_STAGE_DEFINITIONS.slice(0, gateIndex),
          { id: "content_verification", label: "Verify", description: "Independent word check" },
          ...TRACE_STAGE_DEFINITIONS.slice(gateIndex),
        ];
      })();
  const captureEntry: ProcessingTraceStage = (() => {
    const base = statusForStage("capture");
    const hasLiveCapture = source === "recorded" || isRecording || processingState !== "idle";
    return {
      ...base,
      input: hasLiveCapture
        ? { source: inputSource === "upload" ? "Uploaded file" : "Microphone recording", file_name: uploadedAudioName || null }
        : null,
      output: hasLiveCapture && (recordedAudioUrl || outputReady)
        ? { endpoint: "/api/analyze/stream", duration_seconds: recordingDuration || record.duration || null, format: "wav (converted in browser)" }
        : null,
    };
  })();
  return { praat, ai, words, failedWords, canScorePronunciation, contentGate, activeTrace, outputReady, statusForStage, stageDefinitions, captureEntry };
}

export function StageCard({
  id, label, description, entry, dlItems, children,
}: {
  id: string;
  label: string;
  description: string;
  entry?: ProcessingTraceStage;
  dlItems: Array<[string, string]>;
  children?: ReactNode;
}) {
  const status = entry?.status ?? "pending";
  return (
    <article className={`pdebug-layer pdebug-stage-${id}`} data-status={status}>
      <header>
        <span>{traceStatusLabel(status).toUpperCase()}</span>
        <h3>{label}</h3>
      </header>
      <p className="pdebug-note">{description}{entry?.detail ? ` — ${entry.detail}` : ""}</p>
      {dlItems.length > 0 && (
        <dl>
          {dlItems.map(([dt, dd]) => (
            <div key={dt}><dt>{dt}</dt><dd lang="zh-Hant">{dd}</dd></div>
          ))}
        </dl>
      )}
      <JsonPanel label="Input" value={entry?.input ?? "[not available for this record]"} />
      <JsonPanel label="Output" value={entry?.output ?? "[not available for this record]"} />
      {children}
    </article>
  );
}


