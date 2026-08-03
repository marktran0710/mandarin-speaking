import { useEffect, useMemo, useRef, useState } from "react";
import type { AudioRecord } from "./MyStoriesPage";
import { buildSceneReferenceCurves, type SpeechModel } from "../components/StoryRecorder";
import { convertBlobToWav } from "../utils/audio";
import { buildPracticeAnalysisFormData } from "../utils/practiceAnalysis";
import {
  parseDebugAttempt,
  redactDebugValue,
  SAMPLE_DEBUG_RECORD,
  type DebugAttemptSource,
} from "../utils/practiceDebug";
import {
  formatBackendError,
  getBackendUrl,
  readErrorResponse,
} from "../utils/storyRecorderFeedback";
import { loadPublishedTeacherTopics } from "../utils/teacherStories";
import "./TeacherPracticeDebugPage.css";

type JsonObject = Record<string, any>;

const RUBRICS = [
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

function sourceLabel(source: DebugAttemptSource) {
  if (source === "runtime") return "Runtime record";
  if (source === "recorded") return "Live debug recording";
  if (source === "pasted") return "Pasted test case";
  return "Transparent sample";
}

interface RecordedRequestContext {
  scenePrompt: string;
  sceneVocabulary: string;
  sceneImageUrl: string;
  scenePhrases: string;
  sceneSuggestedAnswer: string;
  sceneReferenceCurves: Record<string, number[]> | null;
  asrModel: SpeechModel;
}

type DebugProcessingState = "idle" | "recording" | "uploading" | "processing" | "complete" | "error";
type DebugTraceStatus = "pending" | "running" | "passed" | "integrated" | "review" | "retry" | "skipped" | "failed";

interface ProcessingTraceStage {
  stage: string;
  status: DebugTraceStatus | string;
  duration_ms?: number;
  model?: string | null;
  provider?: string | null;
  detail?: string | null;
  reason_codes?: string[];
}

const TRACE_STAGE_DEFINITIONS = [
  { id: "capture", label: "Record", description: "Microphone input" },
  { id: "preflight", label: "Preflight", description: "Audio quality gate" },
  { id: "asr", label: "ASR", description: "Transcript" },
  { id: "praat", label: "Praat", description: "Acoustic analysis" },
  { id: "feedback", label: "Feedback", description: "AI / local CAF" },
  { id: "quality_gate", label: "Decision", description: "Student next step" },
] as const;

function traceStatusLabel(status: string) {
  if (status === "passed" || status === "integrated") return "Complete";
  if (status === "retry" || status === "failed") return status === "retry" ? "Retry" : "Failed";
  if (status === "review") return "Review";
  if (status === "skipped") return "Skipped";
  if (status === "running") return "Running";
  return "Waiting";
}

function traceDurationLabel(durationMs?: number) {
  if (typeof durationMs !== "number" || !Number.isFinite(durationMs)) return "";
  return durationMs < 1000 ? `${Math.round(durationMs)} ms` : `${(durationMs / 1000).toFixed(1)} s`;
}

function JsonPanel({ value, label }: { value: unknown; label: string }) {
  return (
    <details className="pdebug-json">
      <summary>{label}</summary>
      <pre>{JSON.stringify(redactDebugValue(value), null, 2)}</pre>
    </details>
  );
}

function metric(value: unknown, suffix = "") {
  return typeof value === "number" && Number.isFinite(value)
    ? `${Math.round(value)}${suffix}`
    : "Not available";
}

export default function TeacherPracticeDebugPage({ records }: { records: AudioRecord[] }) {
  const runtimeRecords = useMemo(() => records.filter((record) => record.praatMetrics), [records]);
  const publishedTopics = useMemo(() => loadPublishedTeacherTopics(), []);
  const [selectedTopicId, setSelectedTopicId] = useState(publishedTopics[0]?.id ?? "");
  const [selectedSceneIndex, setSelectedSceneIndex] = useState(0);
  const [asrModel, setAsrModel] = useState<SpeechModel>("ctwhisper");
  const [isRecording, setIsRecording] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const [recordingError, setRecordingError] = useState("");
  const [recordedRecord, setRecordedRecord] = useState<AudioRecord | null>(null);
  const [recordedContext, setRecordedContext] = useState<RecordedRequestContext | null>(null);
  const [recordedAudioUrl, setRecordedAudioUrl] = useState("");
  const [processingState, setProcessingState] = useState<DebugProcessingState>("idle");
  const [processingTrace, setProcessingTrace] = useState<ProcessingTraceStage[]>([]);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const recordingStartedAtRef = useRef(0);
  const durationTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const recordedAudioUrlRef = useRef("");
  const [selectedId, setSelectedId] = useState(runtimeRecords[0]?.id ?? "__sample__");
  const [pastedRecord, setPastedRecord] = useState<AudioRecord | null>(null);
  const [rawJson, setRawJson] = useState("");
  const [parseError, setParseError] = useState("");

  const selectedTopic = publishedTopics.find((topic) => topic.id === selectedTopicId)
    ?? publishedTopics[0];
  const sceneCount = selectedTopic?.images.length ?? 0;

  useEffect(() => {
    return () => {
      if (durationTimerRef.current) clearInterval(durationTimerRef.current);
      streamRef.current?.getTracks().forEach((track) => track.stop());
      if (recordedAudioUrlRef.current) URL.revokeObjectURL(recordedAudioUrlRef.current);
    };
  }, []);

  const stopDurationTimer = () => {
    if (durationTimerRef.current) {
      clearInterval(durationTimerRef.current);
      durationTimerRef.current = null;
    }
  };

  const analyzeRecording = async (rawBlob: Blob) => {
    setIsAnalyzing(true);
    setProcessingState("processing");
    setRecordingError("");
    const topic = selectedTopic;
    const sceneIndex = selectedSceneIndex;
    const context: RecordedRequestContext = {
      scenePrompt: topic?.prompts?.[sceneIndex] || topic?.name || "",
      sceneVocabulary: (topic?.vocabulary?.[sceneIndex] || []).join(", "),
      sceneImageUrl: topic?.images?.[sceneIndex] || "",
      scenePhrases: (topic?.phrases?.[sceneIndex] || []).join("; "),
      sceneSuggestedAnswer: topic?.suggestedAnswers?.[sceneIndex] || "",
      sceneReferenceCurves: topic ? buildSceneReferenceCurves(topic, sceneIndex) : null,
      asrModel,
    };

    try {
      const wavBlob = await convertBlobToWav(rawBlob);
      const formData = buildPracticeAnalysisFormData(wavBlob, {
        asrModel: context.asrModel,
        sceneVocabulary: context.sceneVocabulary,
        scenePrompt: context.scenePrompt,
        sceneImageUrl: context.sceneImageUrl,
        scenePhrases: context.scenePhrases,
        sceneSuggestedAnswer: context.sceneSuggestedAnswer,
        sceneReferenceCurves: context.sceneReferenceCurves,
        sceneAttemptNumber: 1,
      });

      const response = await fetch(`${getBackendUrl()}/api/analyze`, {
        method: "POST",
        body: formData,
        signal: AbortSignal.timeout(120_000),
      });
      if (!response.ok) {
        const body = await readErrorResponse(response);
        throw new Error(body.detail || "Practice analysis failed.");
      }

      const metrics = await response.json();
      const trace = Array.isArray(metrics.processing_trace?.stages)
        ? metrics.processing_trace.stages as ProcessingTraceStage[]
        : [];
      setProcessingTrace(trace);
      const duration = Math.max(
        1,
        Math.floor((Date.now() - recordingStartedAtRef.current) / 1000),
      );
      const nextRecord: AudioRecord = {
        id: `debug-recording-${Date.now()}`,
        timestamp: new Date().toLocaleString(),
        duration,
        transcription: String(metrics.transcription || ""),
        model: context.asrModel,
        topicId: topic?.id,
        imageUrl: context.sceneImageUrl || undefined,
        imageIndex: topic ? sceneIndex : undefined,
        praatMetrics: metrics,
      };

      if (recordedAudioUrlRef.current) URL.revokeObjectURL(recordedAudioUrlRef.current);
      const nextAudioUrl = URL.createObjectURL(wavBlob);
      recordedAudioUrlRef.current = nextAudioUrl;
      setRecordedAudioUrl(nextAudioUrl);
      setRecordedContext(context);
      setRecordedRecord(nextRecord);
      setSelectedId("__recorded__");
      setProcessingState("complete");
    } catch (error) {
      setRecordingError(formatBackendError(error, "the configured backend"));
      setProcessingState("error");
      setProcessingTrace((current) => current.length > 0
        ? current
        : [{ stage: "analysis", status: "failed", detail: "The analysis request failed." }]);
    } finally {
      setIsAnalyzing(false);
    }
  };

  const startRecording = async () => {
    setRecordingError("");
    setProcessingTrace([]);
    setProcessingState("recording");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      audioChunksRef.current = [];
      const preferredType = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "";
      const recorder = new MediaRecorder(
        stream,
        preferredType ? { mimeType: preferredType } : undefined,
      );
      mediaRecorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunksRef.current.push(event.data);
      };
      recorder.onstop = async () => {
        const rawBlob = new Blob(audioChunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        });
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        setProcessingState("uploading");
        await analyzeRecording(rawBlob);
      };
      recordingStartedAtRef.current = Date.now();
      setRecordingDuration(0);
      recorder.start();
      setIsRecording(true);
      durationTimerRef.current = setInterval(() => {
        setRecordingDuration(Math.floor((Date.now() - recordingStartedAtRef.current) / 1000));
      }, 250);
    } catch (error) {
      setRecordingError(error instanceof Error ? error.message : "Could not access the microphone.");
      setProcessingState("error");
    }
  };

  const stopRecording = () => {
    stopDurationTimer();
    setProcessingState("uploading");
    setIsRecording(false);
    if (mediaRecorderRef.current?.state === "recording") mediaRecorderRef.current.stop();
  };

  const selectedRuntime = runtimeRecords.find((record) => record.id === selectedId);
  const record = selectedId === "__recorded__" && recordedRecord
    ? recordedRecord
    : selectedId === "__pasted__" && pastedRecord
    ? pastedRecord
    : selectedRuntime ?? SAMPLE_DEBUG_RECORD;
  const source: DebugAttemptSource = selectedId === "__recorded__" && recordedRecord
    ? "recorded"
    : selectedId === "__pasted__" && pastedRecord
    ? "pasted"
    : selectedRuntime
      ? "runtime"
      : "sample";
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

  const requestPreview = source === "recorded" && recordedContext ? {
    endpoint: "/api/analyze",
    method: "POST multipart/form-data",
    file: "[WAV recorded in this debug session]",
    transcription: "",
    asr_model: recordedContext.asrModel,
    scene_prompt: recordedContext.scenePrompt,
    scene_vocabulary: recordedContext.sceneVocabulary,
    ai_provider: "[backend default]",
    scene_image_url: recordedContext.sceneImageUrl || "[not provided]",
    scene_phrases: recordedContext.scenePhrases || "[not provided]",
    scene_suggested_answer: recordedContext.sceneSuggestedAnswer || "[not provided]",
    scene_attempt_number: 1,
    scene_reference_curves: recordedContext.sceneReferenceCurves || "[not provided]",
  } : {
    endpoint: "/api/analyze",
    method: "POST multipart/form-data",
    file: "[audio bytes are not stored in the debug payload]",
    transcription: record.transcription || praat.transcription || "",
    asr_model: record.model || praat.transcription_model || "",
    scene_prompt: "[not persisted with audio record]",
    scene_vocabulary: "[not persisted with audio record]",
    ai_provider: ai.provider || "[not available]",
    scene_image_url: record.imageUrl || "[not persisted]",
    scene_phrases: "[not persisted with audio record]",
    scene_suggested_answer: "[not persisted with audio record]",
    scene_attempt_number: "[not persisted with audio record]",
    scene_reference_curves: "[not persisted; large arrays omitted]",
  };
  const aiInputPreview = {
    provider: ai.provider || "unknown / fallback",
    transcription: record.transcription || praat.transcription || "",
    scene_prompt: "[not persisted]",
    scene_vocabulary: "[not persisted]",
    scene_image: record.imageUrl
      ? "URL was associated with this record; resolved image bytes are never shown here"
      : "[not persisted]",
    acoustic_patch: {
      tone_accuracy: praat.tone_accuracy,
      fluency_score: praat.fluency_score,
      vowel_quality: praat.vowel_quality,
      pause_analysis: praat.pause_analysis,
    },
    instruction_contract: [
      "Coach beginner Mandarin in Traditional Chinese and return structured JSON.",
      "Compare transcript with scene vocabulary, phrases and the teacher model answer when available.",
      "Vision content is accepted at 60 or above; attempts 1–2 receive a hint and attempt 3+ may reveal the answer.",
    ],
    note: "This is a reconstruction from stored fields, not a captured provider request.",
  };
  const storedTrace = Array.isArray((praat.processing_trace as JsonObject | undefined)?.stages)
    ? (praat.processing_trace as JsonObject).stages as ProcessingTraceStage[]
    : [];
  const activeTrace = processingTrace.length > 0 ? processingTrace : storedTrace;
  const traceByStage = new Map(activeTrace.map((entry) => [entry.stage, entry]));
  const showProcessingTrace = processingState !== "idle" && (
    processingState !== "complete" || activeTrace.length > 0
  );
  const statusForStage = (stageId: string): ProcessingTraceStage => {
    const existing = traceByStage.get(stageId);
    if (existing) return existing;
    if (stageId === "capture") {
      return {
        stage: stageId,
        status: processingState === "recording" ? "running" : "passed",
      };
    }
    if (processingState === "uploading" && stageId === "preflight") {
      return { stage: stageId, status: "running" };
    }
    if (processingState === "processing" && stageId === "preflight") {
      return { stage: stageId, status: "running" };
    }
    if (processingState === "error" && stageId === "quality_gate") {
      return { stage: stageId, status: "failed", detail: recordingError };
    }
    return { stage: stageId, status: "pending" };
  };

  const inspectJson = () => {
    try {
      const next = parseDebugAttempt(rawJson);
      setPastedRecord(next);
      setSelectedId("__pasted__");
      setParseError("");
    } catch (error) {
      setParseError(error instanceof Error ? error.message : "Could not parse this test case.");
    }
  };

  return (
    <section className="pdebug" aria-label="Practice stage debugger">
      <div className="pdebug-callout">
        <div>
          <span className={`pdebug-source pdebug-source-${source}`}>{sourceLabel(source)}</span>
          <h2>Inspect one student Practice attempt end to end</h2>
          <p>Stored results are shown as runtime truth. Inputs that the app does not persist are explicitly marked—not guessed.</p>
        </div>
        <div className="pdebug-picker">
          <label htmlFor="practice-debug-attempt">Attempt / test case</label>
          <select id="practice-debug-attempt" value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>
            {runtimeRecords.map((item) => (
              <option value={item.id} key={item.id}>
                {item.transcription || item.id} · {item.timestamp}
              </option>
            ))}
            {recordedRecord && <option value="__recorded__">Live debug recording</option>}
            {pastedRecord && <option value="__pasted__">Pasted test case</option>}
            <option value="__sample__">Sample attempt (clearly labelled)</option>
          </select>
        </div>
      </div>

      <section className="pdebug-recorder" aria-labelledby="pdebug-recorder-heading">
        <div className="pdebug-recorder-copy">
          <span>LIVE INPUT</span>
          <h3 id="pdebug-recorder-heading">Record a student attempt</h3>
          <p>The microphone audio follows the student recording path: WAV, backend ASR, Praat, then scene-aware feedback.</p>
        </div>
        <div className="pdebug-recorder-controls">
          <label>
            <span>Published story</span>
            <select
              aria-label="Published story"
              value={selectedTopic?.id ?? ""}
              disabled={isRecording || isAnalyzing || publishedTopics.length === 0}
              onChange={(event) => {
                setSelectedTopicId(event.target.value);
                setSelectedSceneIndex(0);
              }}
            >
              {publishedTopics.length === 0 && <option value="">No published story</option>}
              {publishedTopics.map((topic) => <option key={topic.id} value={topic.id}>{topic.name}</option>)}
            </select>
          </label>
          <label>
            <span>Scene</span>
            <select
              aria-label="Scene"
              value={selectedSceneIndex}
              disabled={isRecording || isAnalyzing || sceneCount === 0}
              onChange={(event) => setSelectedSceneIndex(Number(event.target.value))}
            >
              {sceneCount === 0 && <option value={0}>Acoustics only</option>}
              {selectedTopic?.images.map((_, index) => (
                <option key={index} value={index}>Scene {index + 1}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Backend ASR</span>
            <select
              aria-label="Backend ASR"
              value={asrModel}
              disabled={isRecording || isAnalyzing}
              onChange={(event) => setAsrModel(event.target.value as SpeechModel)}
            >
              <option value="ctwhisper">Chinese/Taiwanese Whisper</option>
              <option value="groq">Groq Whisper</option>
              <option value="vibevoice">VibeVoice</option>
            </select>
          </label>
        </div>
        <div className="pdebug-recorder-action">
          <button
            type="button"
            className={isRecording ? "is-recording" : ""}
            disabled={isAnalyzing}
            onClick={isRecording ? stopRecording : startRecording}
          >
            {isRecording ? `Stop & analyze (${recordingDuration}s)` : isAnalyzing ? "Analyzing recording…" : "Start recording"}
          </button>
          {recordedAudioUrl && !isRecording && (
            <audio controls preload="metadata" src={recordedAudioUrl} aria-label="Recorded debug attempt" />
          )}
          {recordingError && <p className="pdebug-error" role="alert">{recordingError}</p>}
        </div>
      </section>

      {showProcessingTrace && (
        <section className={`pdebug-trace pdebug-trace-${processingState}`} aria-labelledby="pdebug-trace-heading">
          <div className="pdebug-trace-heading">
            <div>
              <span>PROCESSING TRACE</span>
              <h3 id="pdebug-trace-heading">
                {processingState === "complete"
                  ? "How this attempt became the result"
                  : processingState === "error"
                    ? "Where processing stopped"
                    : "Processing this student attempt"}
              </h3>
            </div>
            {processingState === "processing" && <span className="pdebug-trace-live">Running</span>}
            {processingState === "complete" && praat.processing_trace && (
              <small>{traceDurationLabel((praat.processing_trace as JsonObject).total_duration_ms as number)}</small>
            )}
          </div>
          <ol className="pdebug-trace-list">
            {TRACE_STAGE_DEFINITIONS.map((definition) => {
              const entry = statusForStage(definition.id);
              return (
                <li key={definition.id} data-status={entry.status}>
                  <span className="pdebug-trace-marker" aria-hidden="true" />
                  <div>
                    <strong>{definition.label}</strong>
                    <span>{definition.description}</span>
                    {entry.detail && <small>{entry.detail}</small>}
                  </div>
                  <em>
                    {traceStatusLabel(entry.status)}
                    {entry.duration_ms !== undefined && ` · ${traceDurationLabel(entry.duration_ms)}`}
                  </em>
                </li>
              );
            })}
          </ol>
          {processingState === "processing" && activeTrace.length === 0 && (
            <p className="pdebug-trace-note">The backend returns the measured stage timings when analysis completes.</p>
          )}
        </section>
      )}

      <details className="pdebug-import">
        <summary>Paste an attempt or /api/analyze response</summary>
        <label htmlFor="practice-debug-json">Test case JSON</label>
        <textarea
          id="practice-debug-json"
          value={rawJson}
          onChange={(event) => setRawJson(event.target.value)}
          placeholder={'{"transcription":"…","praatMetrics":{"tone_accuracy":75,"fluency_score":68}}'}
        />
        <button type="button" onClick={inspectJson}>Inspect JSON</button>
        {parseError && <p className="pdebug-error" role="alert">{parseError}</p>}
        <small>Credentials, auth headers, signed URL tokens and binary/base64 fields are redacted before rendering.</small>
      </details>

      <ol className="pdebug-pipeline" aria-label="Practice processing pipeline">
        <li><strong>1 · Browser</strong><span>WAV + scene context</span></li>
        <li><strong>2 · Preflight / ASR</strong><span>audio quality + transcript</span></li>
        <li><strong>3 · Praat</strong><span>pitch, tones, pauses, fluency</span></li>
        <li><strong>4 · AI / local CAF</strong><span>language + content feedback</span></li>
        <li><strong>5 · Student gates</strong><span>retry, drill or continue</span></li>
      </ol>

      <div className="pdebug-score-grid" aria-label="Attempt score summary">
        <article><span>Tone contour</span><strong>{metric(praat.tone_accuracy, "%")}</strong><small>Praat/tone matcher</small></article>
        <article><span>Fluency</span><strong>{metric(praat.fluency_score, "/100")}</strong><small>CAF + pitch continuity</small></article>
        <article><span>Vocabulary</span><strong>{metric(ai.vocabulary_coverage?.score, "/100")}</strong><small>{ai.provider || "No provider"}</small></article>
        <article><span>Content gate</span><strong>{contentGate}</strong><small>{content.judged === false ? "Placeholder, not a score" : "AI scene comparison"}</small></article>
      </div>

      <div className="pdebug-layer-grid">
        <article className="pdebug-layer">
          <header><span>INPUT</span><h3>Browser → backend</h3></header>
          <dl>
            <div><dt>Record ID</dt><dd>{record.id}</dd></div>
            <div><dt>Topic / scene</dt><dd>{record.topicId || "Not persisted"} / {record.imageIndex ?? "—"}</dd></div>
            <div><dt>Audio duration</dt><dd>{record.duration ? `${record.duration}s` : "Not available"}</dd></div>
            <div><dt>Endpoint</dt><dd><code>POST /api/analyze</code></dd></div>
          </dl>
          <JsonPanel label="Reconstructed multipart fields" value={requestPreview} />
        </article>

        <article className="pdebug-layer">
          <header><span>ASR + SAFETY</span><h3>Can this attempt be judged?</h3></header>
          <dl>
            <div><dt>Transcript model</dt><dd>{praat.transcription_model || record.model || "Not available"}</dd></div>
            <div><dt>Transcript</dt><dd lang="zh-Hant">{praat.transcription || record.transcription || "No transcript"}</dd></div>
            <div><dt>Quality status</dt><dd>{quality.status || "Not persisted in older result"}</dd></div>
            <div><dt>Pronunciation scoreable</dt><dd>{canScorePronunciation ? "Yes" : "No — values gated to zero"}</dd></div>
          </dl>
          <JsonPanel label="feedback_quality output" value={quality} />
        </article>

        <article className="pdebug-layer">
          <header><span>ACOUSTICS</span><h3>Praat input / output</h3></header>
          <p className="pdebug-note"><strong>Input:</strong> the same WAV plus transcript (and optional pinyin/reference curves). Praat receives no API key and makes no language judgement.</p>
          <JsonPanel label="Praat input contract" value={{
            wav_audio: "[same uploaded WAV; bytes are not persisted]",
            transcription: record.transcription || praat.transcription || "",
            pinyin_hint: "[not persisted]",
            reference_word_curves: "[not persisted; optional 100-point normalized curves]",
            extraction_settings: { time_step_seconds: 0.025, pitch_floor_hz: 75, pitch_ceiling_hz: 500 },
          }} />
          <dl>
            <div><dt>Pitch frames</dt><dd>{Array.isArray(praat.pitch_contour) ? praat.pitch_contour.length : 0}</dd></div>
            <div><dt>Speech rate</dt><dd>{typeof praat.speech_rate === "number" ? `${praat.speech_rate.toFixed(2)} syl/s` : "Not available"}</dd></div>
            <div><dt>Words judged</dt><dd>{words.length}</dd></div>
            <div><dt>Words needing drill</dt><dd>{failedWords.length}</dd></div>
          </dl>
          <JsonPanel label="Raw Praat-derived result" value={{
            pitch_contour: praat.pitch_contour,
            formants: praat.formants,
            pitch_statistics: praat.pitch_statistics,
            pause_analysis: praat.pause_analysis,
            word_prosody: praat.word_prosody,
            detected_tone: praat.detected_tone,
            tone_accuracy: praat.tone_accuracy,
            fluency_score: praat.fluency_score,
          }} />
        </article>

        <article className="pdebug-layer">
          <header><span>COACHING</span><h3>AI / local CAF input and output</h3></header>
          <p className="pdebug-note">Provider requests are not logged in audio records. The preview below only shows recoverable fields; the returned feedback is the stored runtime output.</p>
          <JsonPanel label="Reconstructed AI input" value={aiInputPreview} />
          <JsonPanel label="Stored AI/local output" value={ai} />
        </article>

        <article className="pdebug-layer pdebug-layer-wide">
          <header><span>DECISION</span><h3>What the student sees next</h3></header>
          <div className="pdebug-decisions">
            <div data-state={canScorePronunciation ? "pass" : "retry"}>
              <strong>Recording quality</strong>
              <span>{canScorePronunciation ? "Scoreable" : "Retry recording"}</span>
            </div>
            <div data-state={failedWords.length === 0 ? "pass" : "retry"}>
              <strong>Pronunciation mastery</strong>
              <span>{failedWords.length === 0 ? "Passed" : `Drill ${failedWords.length} word${failedWords.length === 1 ? "" : "s"}`}</span>
            </div>
            <div data-state={contentGate === "Passed" || contentGate === "Not judged" ? "pass" : "retry"}>
              <strong>Scene meaning</strong>
              <span>{contentGate}</span>
            </div>
          </div>
          {failedWords.length > 0 && (
            <table className="pdebug-word-table">
              <thead><tr><th>Word</th><th>Tone score</th><th>Weakest syllable</th><th>Verdict</th></tr></thead>
              <tbody>{failedWords.map((word: JsonObject, index: number) => {
                const syllables = Array.isArray(word.syllables) ? word.syllables : [];
                const weakest = syllables.length
                  ? [...syllables].sort((a, b) => Number(a.score) - Number(b.score))[0]
                  : null;
                return (
                  <tr key={`${word.token}-${index}`}>
                    <td lang="zh-Hant">{word.token || `Word ${index + 1}`}</td>
                    <td>{metric(word.tone_accuracy, "%")}</td>
                    <td>{weakest ? `${weakest.char}: ${metric(weakest.score)}` : "Not available"}</td>
                    <td>{word.judged === false ? "Unjudged" : "Below 58 minimum"}</td>
                  </tr>
                );
              })}</tbody>
            </table>
          )}
        </article>
      </div>

      <section className="pdebug-rubrics" aria-labelledby="pdebug-rubrics-heading">
        <div>
          <p className="tdash-view-kicker">Scoring contract</p>
          <h2 id="pdebug-rubrics-heading">Rubrics used by the current pipeline</h2>
          <p>Practice does not collapse everything into one opaque overall score. Acoustic, language and content signals remain separate, then gates determine the next action.</p>
        </div>
        <div className="pdebug-rubric-list">
          {RUBRICS.map((rubric) => (
            <article key={rubric.name}>
              <span>{rubric.owner}</span><h3>{rubric.name}</h3><p>{rubric.rule}</p>
            </article>
          ))}
        </div>
      </section>
    </section>
  );
}
