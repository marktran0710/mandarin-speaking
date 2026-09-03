import { type ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import type { AudioRecord } from "./MyStoriesPage";
import { buildSceneReferenceCurves, type SpeechModel } from "../components/story-recorder/StoryRecorder";
import { convertBlobToWav } from "../utils/audio";
import { buildPracticeAnalysisFormData } from "../utils/practiceAnalysis";
import { SAMPLE_DEBUG_RECORD, type DebugAttemptSource } from "../utils/practiceDebug";
import { formatBackendError, getBackendUrl, readErrorResponse } from "../utils/storyRecorderFeedback";
import { loadPublishedTeacherTopics } from "../utils/teacherStories";
import DebugPipelineDetails from "./teacher-practice-debug/DebugPipelineDetails";
import { AUDIO_PREPARATION_TIMEOUT_MS, BACKEND_ANALYSIS_TIMEOUT_MS, TRACE_STAGE_DEFINITIONS, consumeAnalysisStream, sourceLabel, withTimeout, type AnalysisPhase, type DebugProcessingState, type JsonObject, type ProcessingTraceStage, type RecordedRequestContext } from "./teacher-practice-debug/utils";
import "./TeacherPracticeDebugPage.css";
export default function TeacherPracticeDebugPage({ records }: { records: AudioRecord[] }) {
  const runtimeRecords = useMemo(() => records.filter((record) => record.praatMetrics), [records]);
  const publishedTopics = useMemo(() => loadPublishedTeacherTopics(), []);
  const [selectedTopicId, setSelectedTopicId] = useState(publishedTopics[0]?.id ?? "");
  const [selectedSceneIndex, setSelectedSceneIndex] = useState(0);
  const [asrModel, setAsrModel] = useState<SpeechModel>("ctwhisper");
  const [groqAvailable, setGroqAvailable] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisPhase, setAnalysisPhase] = useState<AnalysisPhase>("idle");
  const [analysisElapsed, setAnalysisElapsed] = useState(0);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const [recordingError, setRecordingError] = useState("");
  const [recordedRecord, setRecordedRecord] = useState<AudioRecord | null>(null);
  const [recordedAudioUrl, setRecordedAudioUrl] = useState("");
  const [uploadedAudioName, setUploadedAudioName] = useState("");
  const [inputSource, setInputSource] = useState<"microphone" | "upload">("microphone");
  const [processingState, setProcessingState] = useState<DebugProcessingState>("idle");
  const [processingTrace, setProcessingTrace] = useState<ProcessingTraceStage[]>([]);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const recordingStartedAtRef = useRef(0);
  const durationTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const recordedAudioUrlRef = useRef("");
  const uploadInputRef = useRef<HTMLInputElement | null>(null);
  const asrChoiceTouchedRef = useRef(false);
  const analysisAbortControllerRef = useRef<AbortController | null>(null);
  const analysisRunIdRef = useRef(0);
  const analysisStartedAtRef = useRef(0);
  const [selectedId, setSelectedId] = useState(runtimeRecords[0]?.id ?? "__sample__");
  const selectedTopic = publishedTopics.find((topic) => topic.id === selectedTopicId)
    ?? publishedTopics[0];
  const sceneCount = selectedTopic?.images.length ?? 0;
  useEffect(() => {
    return () => {
      analysisRunIdRef.current += 1;
      analysisAbortControllerRef.current?.abort();
      if (durationTimerRef.current) clearInterval(durationTimerRef.current);
      streamRef.current?.getTracks().forEach((track) => track.stop());
      if (recordedAudioUrlRef.current) URL.revokeObjectURL(recordedAudioUrlRef.current);
    };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 5_000);
    void (async () => {
      try {
        const response = await fetch(`${getBackendUrl()}/api/ai-providers`, {
          signal: controller.signal,
        });
        if (!response.ok) return;
        const data = await response.json();
        const available = Array.isArray(data.providers) && data.providers.some(
          (provider: JsonObject) => provider.id === "groq" && provider.available === true,
        );
        setGroqAvailable(available);
        if (available && !asrChoiceTouchedRef.current) setAsrModel("groq");
      } catch {} finally {
        clearTimeout(timer);
      }
    })();
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, []);
  useEffect(() => {
    if (!isAnalyzing) return;
    setAnalysisElapsed(0);
    const timer = setInterval(() => {
      setAnalysisElapsed(Math.floor((Date.now() - analysisStartedAtRef.current) / 1000));
    }, 250);
    return () => clearInterval(timer);
  }, [isAnalyzing]);
  const stopDurationTimer = () => {
    if (durationTimerRef.current) {
      clearInterval(durationTimerRef.current);
      durationTimerRef.current = null;
    }
  };
  const upsertTraceStage = (runId: number, stage: ProcessingTraceStage) => {
    if (runId !== analysisRunIdRef.current) return;
    setProcessingTrace((current) => {
      const index = current.findIndex((existing) => existing.stage === stage.stage);
      if (index === -1) return [...current, stage];
      const next = [...current];
      next[index] = stage;
      return next;
    });
  };
  const analyzeRecording = async (rawBlob: Blob, durationOverride?: number) => {
    const runId = ++analysisRunIdRef.current;
    analysisStartedAtRef.current = Date.now();
    setIsAnalyzing(true);
    setAnalysisPhase("preparing");
    setProcessingState("uploading");
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
    let backendTimer: ReturnType<typeof setTimeout> | undefined;
    try {
      const wavBlob = await withTimeout(
        convertBlobToWav(rawBlob),
        AUDIO_PREPARATION_TIMEOUT_MS,
        "This audio file could not be decoded within 30 seconds. Try WAV, MP3, or M4A encoded with a standard codec.",
      );
      if (runId !== analysisRunIdRef.current) return;
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
      setAnalysisPhase("backend");
      setProcessingState("processing");
      const controller = new AbortController();
      analysisAbortControllerRef.current = controller;
      backendTimer = setTimeout(() => controller.abort(), BACKEND_ANALYSIS_TIMEOUT_MS);
      const response = await fetch(`${getBackendUrl()}/api/analyze/stream`, {
        method: "POST",
        body: formData,
        signal: controller.signal,
      });
      if (runId !== analysisRunIdRef.current) return;
      if (!response.ok) {
        const body = await readErrorResponse(response);
        throw new Error(body.detail || "Practice analysis failed.");
      }
      const metrics = await consumeAnalysisStream(response, (stage) => upsertTraceStage(runId, stage));
      if (runId !== analysisRunIdRef.current) return;
      const trace = Array.isArray(metrics.processing_trace?.stages)
        ? metrics.processing_trace.stages as ProcessingTraceStage[]
        : [];
      setProcessingTrace(trace);
      const duration = durationOverride ?? Math.max(
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
      setRecordedRecord(nextRecord);
      setSelectedId("__recorded__");
      setProcessingState("complete");
    } catch (error) {
      if (runId !== analysisRunIdRef.current) return;
      const message = error instanceof DOMException && error.name === "AbortError"
        ? "Backend analysis timed out after 120 seconds. Check the backend log, then retry or choose another ASR source."
        : formatBackendError(error, "the configured backend");
      setRecordingError(message);
      setProcessingState("error");
      setProcessingTrace((current) => current.length > 0
        ? current
        : [{ stage: "analysis", status: "failed", detail: "The analysis request failed." }]);
    } finally {
      if (backendTimer) clearTimeout(backendTimer);
      if (runId === analysisRunIdRef.current) {
        analysisAbortControllerRef.current = null;
        setAnalysisPhase("idle");
        setIsAnalyzing(false);
      }
    }
  };
  const cancelAnalysis = () => {
    analysisRunIdRef.current += 1;
    analysisAbortControllerRef.current?.abort();
    analysisAbortControllerRef.current = null;
    setAnalysisPhase("idle");
    setIsAnalyzing(false);
    setProcessingState("error");
    setRecordingError("Analysis cancelled. You can choose another ASR source and retry.");
    setProcessingTrace([{ stage: "analysis", status: "failed", detail: "Cancelled by teacher." }]);
  };
  const startRecording = async () => {
    setRecordingError("");
    setUploadedAudioName("");
    setInputSource("microphone");
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
  const uploadAudio = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const looksLikeAudio = file.type.startsWith("audio/")
      || /\.(wav|wave|webm|mp3|m4a|ogg|aac|flac)$/i.test(file.name);
    if (!looksLikeAudio) {
      setRecordingError("Choose an audio file such as WAV, MP3, M4A, OGG, or WebM.");
      return;
    }
    setRecordingError("");
    setUploadedAudioName(file.name);
    setInputSource("upload");
    setProcessingTrace([]);
    setProcessingState("uploading");
    recordingStartedAtRef.current = Date.now();
    await analyzeRecording(file);
  };
  const selectedRuntime = runtimeRecords.find((record) => record.id === selectedId);
  const record = selectedId === "__recorded__" && recordedRecord
    ? recordedRecord
    : selectedRuntime ?? SAMPLE_DEBUG_RECORD;
  const source: DebugAttemptSource = selectedId === "__recorded__" && recordedRecord
    ? "recorded"
    : selectedRuntime
      ? "runtime"
      : "sample";
  const selectedSourceLabel = source === "recorded" && inputSource === "upload"
    ? "Uploaded debug audio"
    : sourceLabel(source);
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
  const activeTrace = processingState !== "idle"
    ? processingTrace
    : storedTrace;
  const traceByStage = new Map(activeTrace.map((entry) => [entry.stage, entry]));
  const outputReady = processingState === "idle" || processingState === "complete";
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
  const hasVerificationStage = activeTrace.some((entry) => entry.stage === "content_verification");
  const stageDefinitions = useMemo(() => {
    if (!hasVerificationStage) return TRACE_STAGE_DEFINITIONS;
    const gateIndex = TRACE_STAGE_DEFINITIONS.findIndex((definition) => definition.id === "quality_gate");
    return [
      ...TRACE_STAGE_DEFINITIONS.slice(0, gateIndex),
      { id: "content_verification", label: "Verify", description: "Independent word check" },
      ...TRACE_STAGE_DEFINITIONS.slice(gateIndex),
    ];
  }, [hasVerificationStage]);
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
  return (
    <section className="pdebug" aria-label="Practice stage debugger">
      <div className="pdebug-callout">
        <div>
          <span className={`pdebug-source pdebug-source-${source}`}>{selectedSourceLabel}</span>
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
            {recordedRecord && (
              <option value="__recorded__">
                {inputSource === "upload" ? "Uploaded debug audio" : "Live debug recording"}
              </option>
            )}
            <option value="__sample__">Sample attempt (clearly labelled)</option>
          </select>
        </div>
      </div>
      <section className="pdebug-recorder" aria-labelledby="pdebug-recorder-heading">
        <div className="pdebug-recorder-copy">
          <span>LIVE INPUT</span>
          <h3 id="pdebug-recorder-heading">Record or upload a student attempt</h3>
          <p>Microphone and uploaded audio follow the same student path: WAV, backend ASR, Praat, then scene-aware feedback.</p>
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
              onChange={(event) => {
                asrChoiceTouchedRef.current = true;
                setAsrModel(event.target.value as SpeechModel);
              }}
            >
              <option value="groq" disabled={!groqAvailable}>
                {groqAvailable ? "Groq Whisper — recommended free API" : "Groq Whisper — unavailable"}
              </option>
              <option value="ctwhisper">Chinese/Taiwanese Whisper — local fallback</option>
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
            {isRecording
              ? `Stop & analyze (${recordingDuration}s)`
              : isAnalyzing
                ? analysisPhase === "preparing"
                  ? `Preparing audio… ${analysisElapsed}s`
                  : `Analyzing with ${asrModel === "groq" ? "Groq" : asrModel}… ${analysisElapsed}s`
                : "Start recording"}
          </button>
          <button
            type="button"
            className="pdebug-upload-button"
            disabled={isRecording || isAnalyzing}
            onClick={() => uploadInputRef.current?.click()}
          >
            Upload audio
          </button>
          {isAnalyzing && (
            <button type="button" className="pdebug-cancel-button" onClick={cancelAnalysis}>
              Cancel
            </button>
          )}
          <input
            ref={uploadInputRef}
            className="pdebug-audio-upload-input"
            type="file"
            accept="audio/*,.wav,.wave,.webm,.mp3,.m4a,.ogg,.aac,.flac"
            aria-label="Upload audio file"
            disabled={isRecording || isAnalyzing}
            onChange={uploadAudio}
          />
          {uploadedAudioName && inputSource === "upload" && (
            <small className="pdebug-upload-name">{uploadedAudioName}</small>
          )}
          {recordedAudioUrl && !isRecording && (
            <audio controls preload="metadata" src={recordedAudioUrl} aria-label="Recorded debug attempt" />
          )}
          {recordingError && <p className="pdebug-error" role="alert">{recordingError}</p>}
        </div>
      </section>
      <DebugPipelineDetails
        stageDefinitions={stageDefinitions}
        inputSource={inputSource}
        processingState={processingState}
        analysisPhase={analysisPhase}
        analysisElapsed={analysisElapsed}
        activeTrace={activeTrace}
        praat={praat}
        ai={ai}
        outputReady={outputReady}
        captureEntry={captureEntry}
        statusForStage={statusForStage}
        record={record}
        words={words}
        contentGate={contentGate}
        canScorePronunciation={canScorePronunciation}
        failedWords={failedWords}
      />
    </section>
  );
}
