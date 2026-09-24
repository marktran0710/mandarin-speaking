import { type ChangeEvent, useEffect, useRef, useState } from "react";
import type { AudioRecord } from "../types/audioRecord";
import { buildSceneReferenceCurves, type SpeechModel } from "../components/story-recorder/StoryRecorder";
import { convertBlobToWav } from "../utils/audio";
import { buildPracticeAnalysisFormData } from "../utils/practiceAnalysis";
import { formatBackendError, getBackendUrl, readErrorResponse } from "../utils/storyRecorderFeedback";
import { canUseDatabase, listCustomStories } from "../services/database";
import { publishedTopicsFromStories } from "../utils/teacherStories";
import type { Topic } from "../components/content/topic-selector/types";
import DebugPipelineDetails from "./teacher-practice-debug/DebugPipelineDetails";
import {
  AUDIO_PREPARATION_TIMEOUT_MS, BACKEND_ANALYSIS_TIMEOUT_MS, consumeAnalysisStream, derivePipelineView, metric, withTimeout,
  type DebugProcessingState, type ProcessingTraceStage,
} from "./teacher-practice-debug/utils";
import "./TeacherPracticeDebugPage.css";
import "./AdminAsrComparePage.css";

const CANDIDATES: Array<{ model: SpeechModel; label: string; note: string }> = [
  { model: "ctwhisper", label: "Chinese/Taiwanese Whisper", note: "Local — free" },
  { model: "openai", label: "OpenAI Whisper (whisper-1)", note: "Cloud — ~$0.006/min" },
];

interface ColumnState {
  processingState: DebugProcessingState;
  processingTrace: ProcessingTraceStage[];
  record: AudioRecord | null;
  error: string;
  elapsedMs: number;
}

const IDLE_COLUMN: ColumnState = { processingState: "idle", processingTrace: [], record: null, error: "", elapsedMs: 0 };

/** Runs the SAME recording through the real /api/analyze/stream pipeline once
 * per ASR candidate, side by side, so a teacher can compare transcript AND
 * every downstream score (Praat, feedback, gates) — not just raw text — the
 * same way the student-facing flow would score each one. */
export default function AdminAsrComparePage() {
  const [publishedTopics, setPublishedTopics] = useState<Topic[]>([]);
  const [selectedTopicId, setSelectedTopicId] = useState(publishedTopics[0]?.id ?? "");
  const [selectedSceneIndex, setSelectedSceneIndex] = useState(0);
  const [uploadedAudioName, setUploadedAudioName] = useState("");
  const [isComparing, setIsComparing] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [columns, setColumns] = useState<Record<SpeechModel, ColumnState>>({
    ctwhisper: IDLE_COLUMN,
    openai: IDLE_COLUMN,
  } as Record<SpeechModel, ColumnState>);
  const uploadInputRef = useRef<HTMLInputElement | null>(null);
  const runIdRef = useRef(0);

  useEffect(() => {
    if (!canUseDatabase()) return;
    let active = true;
    void listCustomStories()
      .then((stories) => {
        if (active) setPublishedTopics(publishedTopicsFromStories(stories));
      })
      .catch(() => {
        if (active) setPublishedTopics([]);
      });
    return () => {
      active = false;
    };
  }, []);

  const selectedTopic = publishedTopics.find((topic) => topic.id === selectedTopicId) ?? publishedTopics[0];
  const sceneCount = selectedTopic?.images.length ?? 0;

  const updateColumn = (runId: number, model: SpeechModel, patch: Partial<ColumnState>) => {
    if (runId !== runIdRef.current) return;
    setColumns((current) => ({ ...current, [model]: { ...current[model], ...patch } }));
  };

  const runOne = async (runId: number, model: SpeechModel, wavBlob: Blob, startedAt: number) => {
    updateColumn(runId, model, { processingState: "uploading", processingTrace: [], error: "" });
    const topic = selectedTopic;
    const sceneIndex = selectedSceneIndex;
    const formData = buildPracticeAnalysisFormData(wavBlob, {
      asrModel: model,
      sceneVocabulary: (topic?.vocabulary?.[sceneIndex] || []).join(", "),
      scenePrompt: topic?.prompts?.[sceneIndex] || topic?.name || "",
      sceneImageUrl: topic?.images?.[sceneIndex] || "",
      scenePhrases: (topic?.phrases?.[sceneIndex] || []).join("; "),
      sceneSuggestedAnswer: topic?.suggestedAnswers?.[sceneIndex] || "",
      sceneReferenceCurves: topic ? buildSceneReferenceCurves(topic, sceneIndex) : null,
      sceneAttemptNumber: 1,
    });
    updateColumn(runId, model, { processingState: "processing" });
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), BACKEND_ANALYSIS_TIMEOUT_MS);
    try {
      const response = await fetch(`${getBackendUrl()}/api/analyze/stream`, {
        method: "POST",
        body: formData,
        signal: controller.signal,
      });
      if (runId !== runIdRef.current) return;
      if (!response.ok) {
        const body = await readErrorResponse(response);
        throw new Error(body.detail || "Analysis failed.");
      }
      const metrics = await consumeAnalysisStream(response, (stage) => {
        if (runId !== runIdRef.current) return;
        setColumns((current) => {
          const existingIndex = current[model].processingTrace.findIndex((entry) => entry.stage === stage.stage);
          const nextTrace = existingIndex === -1
            ? [...current[model].processingTrace, stage]
            : current[model].processingTrace.map((entry, index) => index === existingIndex ? stage : entry);
          return { ...current, [model]: { ...current[model], processingTrace: nextTrace } };
        });
      });
      if (runId !== runIdRef.current) return;
      const record: AudioRecord = {
        id: `asr-compare-${model}-${Date.now()}`,
        timestamp: new Date().toLocaleString(),
        duration: Math.round(wavBlob.size / 32000),
        transcription: String(metrics.transcription || ""),
        model,
        praatMetrics: metrics,
      };
      updateColumn(runId, model, { processingState: "complete", record, elapsedMs: Date.now() - startedAt });
    } catch (error) {
      if (runId !== runIdRef.current) return;
      const message = error instanceof DOMException && error.name === "AbortError"
        ? `Timed out after ${BACKEND_ANALYSIS_TIMEOUT_MS / 1000}s.`
        : formatBackendError(error, "the configured backend");
      updateColumn(runId, model, {
        processingState: "error",
        error: message,
        elapsedMs: Date.now() - startedAt,
        processingTrace: [{ stage: "analysis", status: "failed", detail: message }],
      });
    } finally {
      clearTimeout(timer);
    }
  };

  const compareFile = async (file: File) => {
    const runId = ++runIdRef.current;
    setUploadError("");
    setUploadedAudioName(file.name);
    setIsComparing(true);
    setColumns({ ctwhisper: IDLE_COLUMN, openai: IDLE_COLUMN } as Record<SpeechModel, ColumnState>);
    try {
      const wavBlob = await withTimeout(
        convertBlobToWav(file),
        AUDIO_PREPARATION_TIMEOUT_MS,
        "This audio file could not be decoded within 30 seconds. Try WAV, MP3, or M4A encoded with a standard codec.",
      );
      if (runId !== runIdRef.current) return;
      const startedAt = Date.now();
      await Promise.allSettled(CANDIDATES.map((candidate) => runOne(runId, candidate.model, wavBlob, startedAt)));
    } catch (error) {
      if (runId !== runIdRef.current) return;
      setUploadError(error instanceof Error ? error.message : "Could not read this audio file.");
    } finally {
      if (runId === runIdRef.current) setIsComparing(false);
    }
  };

  const onUpload = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const looksLikeAudio = file.type.startsWith("audio/") || /\.(wav|wave|webm|mp3|m4a|ogg|aac|flac)$/i.test(file.name);
    if (!looksLikeAudio) {
      setUploadError("Choose an audio file such as WAV, MP3, M4A, OGG, or WebM.");
      return;
    }
    void compareFile(file);
  };

  const bothComplete = CANDIDATES.every((candidate) => columns[candidate.model].processingState === "complete");
  const transcriptsMatch = bothComplete
    && columns.ctwhisper.record?.transcription.trim() === columns.openai.record?.transcription.trim();

  const rows = CANDIDATES.map((candidate) => {
    const column = columns[candidate.model];
    const record = column.record ?? { id: "pending", timestamp: "", duration: 0, transcription: "", model: candidate.model } as AudioRecord;
    const view = derivePipelineView({
      record,
      source: "recorded",
      processingState: column.processingState,
      processingTrace: column.processingTrace,
      isRecording: false,
      inputSource: "upload",
      uploadedAudioName,
      recordedAudioUrl: "",
      recordingDuration: 0,
      recordingError: column.error,
    });
    return { candidate, column, record, view };
  });

  return (
    <section className="asr-compare" aria-label="ASR model comparison">
      <div className="pdebug-callout asr-compare-callout">
        <div>
          <h2>Compare ASR models on the real scoring pipeline</h2>
          <p>Upload one recording — it runs through the exact same /api/analyze pipeline (Praat, feedback, gates) once per model, so the two results are directly comparable, not just the raw transcript.</p>
        </div>
        <div className="pdebug-picker">
          <label htmlFor="asr-compare-story">Published story</label>
          <select
            id="asr-compare-story"
            value={selectedTopic?.id ?? ""}
            disabled={isComparing || publishedTopics.length === 0}
            onChange={(event) => { setSelectedTopicId(event.target.value); setSelectedSceneIndex(0); }}
          >
            {publishedTopics.length === 0 && <option value="">No published story</option>}
            {publishedTopics.map((topic) => <option key={topic.id} value={topic.id}>{topic.name}</option>)}
          </select>
        </div>
        <div className="pdebug-picker">
          <label htmlFor="asr-compare-scene">Scene</label>
          <select
            id="asr-compare-scene"
            value={selectedSceneIndex}
            disabled={isComparing || sceneCount === 0}
            onChange={(event) => setSelectedSceneIndex(Number(event.target.value))}
          >
            {sceneCount === 0 && <option value={0}>Acoustics only</option>}
            {selectedTopic?.images.map((_, index) => <option key={index} value={index}>Scene {index + 1}</option>)}
          </select>
        </div>
      </div>

      <div className="asr-compare-upload">
        <button type="button" className="pdebug-upload-button" disabled={isComparing} onClick={() => uploadInputRef.current?.click()}>
          {isComparing ? "Comparing…" : "Upload audio to compare"}
        </button>
        <input
          ref={uploadInputRef}
          className="pdebug-audio-upload-input"
          type="file"
          accept="audio/*,.wav,.wave,.webm,.mp3,.m4a,.ogg,.aac,.flac"
          aria-label="Upload audio file to compare"
          disabled={isComparing}
          onChange={onUpload}
        />
        {uploadedAudioName && <small className="pdebug-upload-name">{uploadedAudioName}</small>}
        {uploadError && <p className="pdebug-error" role="alert">{uploadError}</p>}
      </div>

      {bothComplete && (
        <p className={`asr-compare-summary ${transcriptsMatch ? "is-match" : "is-mismatch"}`}>
          {transcriptsMatch ? "Both models transcribed the same text." : "Transcripts differ between models — see below."}
          {" "}ctwhisper: {(columns.ctwhisper.elapsedMs / 1000).toFixed(1)}s · openai: {(columns.openai.elapsedMs / 1000).toFixed(1)}s
        </p>
      )}

      {uploadedAudioName && (
        <table className="asr-compare-table">
          <thead>
            <tr>
              <th scope="col">Metric</th>
              {rows.map(({ candidate }) => <th scope="col" key={candidate.model}>{candidate.label}</th>)}
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">Transcript</th>
              {rows.map(({ candidate, record }) => <td key={candidate.model} lang="zh-Hant">{record.transcription || "—"}</td>)}
            </tr>
            <tr>
              <th scope="row">Time</th>
              {rows.map(({ candidate, column }) => (
                <td key={candidate.model}>{column.processingState === "complete" || column.processingState === "error" ? `${(column.elapsedMs / 1000).toFixed(1)}s` : "—"}</td>
              ))}
            </tr>
            <tr>
              <th scope="row">Tone accuracy</th>
              {rows.map(({ candidate, view }) => <td key={candidate.model}>{metric(view.praat.tone_accuracy, "%")}</td>)}
            </tr>
            <tr>
              <th scope="row">Fluency</th>
              {rows.map(({ candidate, view }) => <td key={candidate.model}>{metric(view.praat.fluency_score, "/100")}</td>)}
            </tr>
            <tr>
              <th scope="row">Speech rate</th>
              {rows.map(({ candidate, view }) => (
                <td key={candidate.model}>{typeof view.praat.speech_rate === "number" ? `${view.praat.speech_rate.toFixed(2)} syl/s` : "Not available"}</td>
              ))}
            </tr>
            <tr>
              <th scope="row">Vocabulary</th>
              {rows.map(({ candidate, view }) => <td key={candidate.model}>{metric(view.ai.vocabulary_coverage?.score, "/100")}</td>)}
            </tr>
            <tr>
              <th scope="row">Pronunciation scoreable</th>
              {rows.map(({ candidate, view, column }) => (
                <td key={candidate.model}>{column.processingState === "complete" ? (view.canScorePronunciation ? "Yes" : "No") : "—"}</td>
              ))}
            </tr>
            <tr>
              <th scope="row">Content gate</th>
              {rows.map(({ candidate, view, column }) => <td key={candidate.model}>{column.processingState === "complete" ? view.contentGate : "—"}</td>)}
            </tr>
          </tbody>
        </table>
      )}

      <div className="asr-compare-grid">
        {rows.map(({ candidate, column, record, view }) => {
          return (
            <article key={candidate.model} className="asr-compare-column">
              <header className="asr-compare-column-header">
                <h3>{candidate.label}</h3>
                <span>{candidate.note}</span>
              </header>
              {column.error && <p className="pdebug-error" role="alert">{column.error}</p>}
              <DebugPipelineDetails
                stageDefinitions={view.stageDefinitions}
                inputSource="upload"
                processingState={column.processingState}
                analysisPhase={column.processingState === "uploading" ? "preparing" : "backend"}
                analysisElapsed={Math.round(column.elapsedMs / 1000)}
                activeTrace={view.activeTrace}
                praat={view.praat}
                ai={view.ai}
                outputReady={view.outputReady}
                captureEntry={view.captureEntry}
                statusForStage={view.statusForStage}
                record={record}
                words={view.words}
                contentGate={view.contentGate}
                canScorePronunciation={view.canScorePronunciation}
                failedWords={view.failedWords}
              />
            </article>
          );
        })}
      </div>
    </section>
  );
}
