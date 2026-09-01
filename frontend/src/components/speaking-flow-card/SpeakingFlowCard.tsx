import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { BiLabel } from "../BiLabel";
import AppButton from "../AppButton";
import SpeakingResultsFlow from "./SpeakingResultsFlow";
import { sceneReady } from "../../utils/storyRecorderFeedback";
import type { SelfEvalLevel } from "../../utils/selfEvalComparison";
import type {
  PraatMetrics,
  SpeechModel,
} from "../story-recorder/StoryRecorder";
import ModelRecordingPractice from "./ModelRecordingPractice";
import StudentIcon from "../StudentIcon";
import "./SpeakingFlowCard.css";

const MAX_RECORDING_SECONDS = 30;

interface SceneProgressEntry {
  attempts: number;
  bestTone: number;
  bestFluency: number;
}

interface SpeakingFlowCardProps {
  selectedImage: string;
  selectedImageIndex: number;
  totalScenes: number;
  modelSentence?: string;
  /** Model-voice reference audio for the whole scene sentence (TTS or a
   * teacher's own recording) — lets the student hear the target before
   * recording, the same real voice the scoring engine now grades against. */
  modelAudioUrl?: string;
  prog?: SceneProgressEntry;
  praatMetrics: PraatMetrics | null;
  analysisAudioBlob: Blob | null;
  error: string | null;
  isRecording: boolean;
  isBusy: boolean;
  isTranscribing: boolean;
  isAnalyzing: boolean;
  recordingDuration: number;
  silenceDuration: number;
  selectedModel: SpeechModel;
  groqAvailable: boolean;
  openaiAvailable: boolean;
  onSelectedModelChange: (model: SpeechModel) => void;
  recordingButtonDisabled: boolean;
  onPrimaryRecordingAction: () => void;
  onSubmitVoiceFile: (event: ChangeEvent<HTMLInputElement>) => void;
  pendingUploadName?: string;
  pendingUploadUrl?: string;
  onAnalyzePendingUpload?: () => void;
  onClearPendingUpload?: () => void;
  /** Pronunciation mastery gate: true once a full-sentence recording had
   * every word clear the per-syllable pass verdict. */
  masteryPassed: boolean;
  /** The recording says the intended scene and contains all required words. */
  contentPassed: boolean;
  /** Words from the latest failing recording the student has since drilled
   * back to a pass — drives the words-first-then-sentence checklist. */
  clearedWords: string[];
  onWordDrillPass: (token: string) => void;
  onSelfEvalSubmit?: (levels: {
    content: SelfEvalLevel;
    pronunciation: SelfEvalLevel;
  }) => void;
  hasNextScene: boolean;
  onNextScene: () => void;
  onViewSummary: () => void;
  /** PART 3 of the small-teacher-validated-pilot architecture: when true,
   * bypasses `sceneReady`'s legacy bestTone/bestFluency/attempts>=4 gate for
   * THIS attempt — set only for a pilot session where the backend actually
   * computed the assistive-feedback layer (see StoryRecorder's
   * `pilotAssistiveFeedbackActive`). `masteryPassed` gets the same
   * per-attempt override upstream, so together they mean legacy scoring
   * never blocks a pilot student's progression. Defaults to false: no
   * behavior change until an operator turns the pilot flag on. */
  sceneReadyOverride?: boolean;
}

/** The Speaking step as a two-screen app flow inside one fixed-height card:
 *
 *   record  →  (analyzing)  →  results flow  →  next scene / record again
 *
 * The results screen *replaces* the record controls, so a student always
 * passes through their feedback before acting. What used to be one dense
 * results readout is now SpeakingResultsFlow — a guided overview → fix →
 * practice mini-flow; this component keeps only the record screen, the
 * analyzing overlay, and the record ⇄ results switching. */
export default function SpeakingFlowCard({
  selectedImage,
  selectedImageIndex,
  totalScenes,
  modelSentence,
  modelAudioUrl,
  prog,
  praatMetrics,
  analysisAudioBlob,
  error,
  isRecording,
  isBusy,
  isTranscribing,
  isAnalyzing,
  recordingDuration,
  selectedModel,
  groqAvailable,
  openaiAvailable,
  onSelectedModelChange,
  recordingButtonDisabled,
  onPrimaryRecordingAction,
  onSubmitVoiceFile,
  pendingUploadName,
  pendingUploadUrl,
  onAnalyzePendingUpload = () => undefined,
  onClearPendingUpload = () => undefined,
  masteryPassed,
  contentPassed,
  clearedWords,
  onWordDrillPass,
  onSelfEvalSubmit,
  hasNextScene,
  onNextScene,
  onViewSummary,
  sceneReadyOverride = false,
}: SpeakingFlowCardProps) {
  const [screen, setScreen] = useState<"record" | "results">("record");
  const uploadInputRef = useRef<HTMLInputElement>(null);

  // Flip to results exactly when an analysis finishes (busy → idle with
  // fresh metrics) — not merely "metrics exist", which would trap the
  // student on the results screen after choosing to record again.
  const wasBusy = useRef(false);
  const lastMetricsRef = useRef<PraatMetrics | null>(praatMetrics);
  useEffect(() => {
    if (isBusy) {
      wasBusy.current = true;
    }
    const hasFreshMetrics = Boolean(praatMetrics && praatMetrics !== lastMetricsRef.current);
    if (!isBusy && praatMetrics && (wasBusy.current || hasFreshMetrics)) {
      setScreen("results");
      wasBusy.current = false;
    }
    lastMetricsRef.current = praatMetrics;
  }, [isBusy, praatMetrics]);

  // Switching scenes shows that scene's last result if it has one (praatMetrics
  // is already cached per scene by the parent), instead of always dropping
  // back to the record screen and losing the student's earlier attempt.
  useEffect(() => {
    setScreen(praatMetrics ? "results" : "record");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedImageIndex]);

  const attempts = prog?.attempts ?? 0;
  const bestToneValue =
    attempts > 0 && prog?.bestTone !== undefined
      ? `${Math.round(prog.bestTone)}%`
      : "–";
  // Keep the verdict-driven results presentation intact. Continuing is
  // separate: one completed analysis is enough to move on.
  const ready =
    (sceneReadyOverride || (prog ? sceneReady(prog) : false)) &&
    masteryPassed &&
    contentPassed;
  const canContinue = Boolean(praatMetrics);

  const sceneChip = (
    <span className="sfc-attempt-only">
      <BiLabel
        zh={`部分 ${selectedImageIndex + 1}/${totalScenes}`}
        en={`Scene ${selectedImageIndex + 1} of ${totalScenes}`}
      />
    </span>
  );

  // ── Analyzing overlay (either screen) ─────────────────────────────────
  if (isTranscribing || isAnalyzing) {
    return (
      <section className="speaking-flow-card sfc-analyzing sfc-screen" aria-label="Analyzing recording">
        <div className="practice-workspace">
          <div className="practice-scene-col">
            <div className="practice-scene-image">
              <img src={selectedImage} alt={`Scene ${selectedImageIndex + 1}`} />
            </div>
          </div>

          <div className="sfc-analyzing-main">
            <div className="analysis-loading-card sfc-loading">
              <div className="analysis-loading-spinner" />
              <div className="analysis-loading-text">
                <p className="analysis-loading-title">
                  {isTranscribing ? (
                    <BiLabel k="listening_to_your_voice" />
                  ) : (
                    <BiLabel k="analyzing_pronunciation" />
                  )}
                </p>
                <p className="analysis-loading-sub">
                  {isTranscribing ? (
                    <BiLabel k="converting_speech_to_text" />
                  ) : (
                    <BiLabel k="checking_tones_rhythm_and_vocabulary" />
                  )}
                </p>
              </div>
              <div className="analysis-loading-steps">
                <span className={`loading-step ${isTranscribing ? "active" : "done"}`}>
                  <BiLabel k="transcribe" />
                </span>
                <span className="loading-step-arrow" aria-hidden="true"><StudentIcon name="arrow-right" size={16} /></span>
                <span className={`loading-step ${isAnalyzing && !isTranscribing ? "active" : ""}`}>
                  Praat
                </span>
                <span className="loading-step-arrow" aria-hidden="true"><StudentIcon name="arrow-right" size={16} /></span>
                <span className="loading-step">
                  <BiLabel k="feedback" />
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>
    );
  }

  // ── Screen 1: record ──────────────────────────────────────────────────
  if (screen === "record" || !praatMetrics) {
    return (
      <section className="speaking-flow-card sfc-screen sfc-record" aria-label="Record your story">
        <div className="practice-workspace">
        <div className="practice-scene-col">
          <div className="practice-scene-image">
            <img src={selectedImage} alt={`Scene ${selectedImageIndex + 1}`} />
          </div>
          {sceneChip}
        </div>

        <div className="sfc-record-main">
        <div className="sfc-record-panel">
            <ModelRecordingPractice
              sceneIndex={selectedImageIndex}
              modelSentence={modelSentence}
              modelAudioUrl={modelAudioUrl}
            />

            <details className="sfc-recording-options">
              <summary>Recording options</summary>
              <label className="sfc-speech-source">
                <span>Speech source</span>
                <select
                  aria-label="Speech source"
                  value={selectedModel}
                  disabled={isBusy}
                  onChange={(event) =>
                    onSelectedModelChange(event.target.value as SpeechModel)
                  }
                >
                  <option value="groq" disabled={!groqAvailable}>
                    {groqAvailable
                      ? "Groq Whisper — recommended free API"
                      : "Groq Whisper — unavailable (API key required)"}
                  </option>
                  <option value="openai" disabled={!openaiAvailable}>
                    {openaiAvailable
                      ? "OpenAI Whisper — cloud API"
                      : "OpenAI Whisper — unavailable (API key required)"}
                  </option>
                  <option value="webspeech">Browser Speech — free fallback</option>
                  <option value="ctwhisper">Chinese/Taiwanese Whisper — local</option>
                  <option value="vibevoice">VibeVoice — experimental local</option>
                </select>
              </label>
              <p className="sfc-speech-source-note">
                {selectedModel === "groq"
                  ? "Recommended: fast, stable Mandarin transcription through the configured free API tier."
                  : selectedModel === "openai"
                    ? "Uses OpenAI's Whisper API; requires a configured key and is a paid cloud service."
                    : selectedModel === "webspeech"
                      ? "Uses the browser's live speech service; availability depends on the browser and network."
                      : selectedModel === "ctwhisper"
                        ? "Runs the local Chinese/Taiwanese Whisper model; private but slower on CPU."
                        : "Experimental local model; its first run may take several minutes to load."}
              </p>
            </details>
            <div className="sfc-record-actions" aria-label="Recording actions">
            <AppButton
              tone={isRecording ? "danger" : "primary"}
              size="lg"
              onClick={onPrimaryRecordingAction}
              disabled={recordingButtonDisabled || Boolean(pendingUploadName)}
              className={`sfc-record-btn${isRecording ? " is-recording" : ""}`}
              aria-label={isRecording ? "Stop Recording" : undefined}
              aria-pressed={isRecording}
            >
              <span className="sfc-record-icon" aria-hidden="true">
                <StudentIcon name={isRecording ? "stop" : "record"} size={18} />
              </span>
              {isRecording ? (
                <>
                  <BiLabel k="stop_recording" />
                  <span className="sfc-record-btn-timer" aria-live="polite">
                    {recordingDuration} / {MAX_RECORDING_SECONDS}s
                  </span>
                </>
              ) : (
                <BiLabel k="record" />
              )}
            </AppButton>

            <div className="sfc-secondary-actions">
              <AppButton
                tone="subtle"
                size="sm"
                className="sfc-upload-btn"
                onClick={() => uploadInputRef.current?.click()}
                disabled={isBusy || Boolean(pendingUploadName)}
              >
                <StudentIcon name="upload" size={18} />
                <BiLabel k="upload_audio" />
              </AppButton>
              <input
                ref={uploadInputRef}
                className="submit-voice-input"
                type="file"
                accept="audio/*,.wav,.wave,.webm,.mp3,.m4a,.ogg"
                onChange={onSubmitVoiceFile}
                disabled={isBusy}
                tabIndex={-1}
              />
            </div>
            {pendingUploadName && pendingUploadUrl && (
              <div className="sfc-pending-upload" aria-label="Audio ready for analysis">
                <div className="sfc-pending-upload-copy">
                  <strong>Audio ready</strong>
                  <span>{pendingUploadName}</span>
                </div>
                <audio controls src={pendingUploadUrl} />
                <div className="sfc-pending-upload-actions">
                  <AppButton tone="primary" size="sm" onClick={onAnalyzePendingUpload}>
                    Analyze audio
                  </AppButton>
                  <button type="button" className="sfc-clear-upload" onClick={onClearPendingUpload}>
                    Remove
                  </button>
                </div>
              </div>
            )}
            </div>
            <div className="stat-row" aria-label="Speaking practice statistics">
              <div className="stat-chip stat-neutral">
                <div className="label">
                  <BiLabel zh="嘗試次數" pinyin="Chángshì cìshù" en="Attempts" />
                </div>
                <div className="value">{attempts}</div>
              </div>
              <div className="stat-chip stat-neutral">
                <div className="label">
                  <BiLabel zh="最佳聲調" pinyin="Zuìjiā shēngdiào" en="Best tone" />
                </div>
                <div className="value">{bestToneValue}</div>
              </div>
            </div>
            {error && <p className="sfc-error">{error}</p>}
          </div>
        </div>
        </div>
      </section>
    );
  }

  // ── Screen 2: results — the guided overview → fix → practice flow.
  // Keyed per scene + attempt so a fresh analysis always restarts the flow
  // on its overview step (and drops any stale step/focus state). ──────────
  return (
    <SpeakingResultsFlow
      key={`${selectedImageIndex}-${attempts}`}
      selectedImage={selectedImage}
      selectedImageIndex={selectedImageIndex}
      totalScenes={totalScenes}
      modelSentence={modelSentence}
      modelAudioUrl={modelAudioUrl}
      attempts={attempts}
      ready={ready}
      canContinue={canContinue}
      masteryPassed={masteryPassed}
      praatMetrics={praatMetrics}
      analysisAudioBlob={analysisAudioBlob}
      clearedWords={clearedWords}
      onWordDrillPass={onWordDrillPass}
      onSelfEvalSubmit={onSelfEvalSubmit}
      hasNextScene={hasNextScene}
      onNextScene={onNextScene}
      onViewSummary={onViewSummary}
      onRecordAgain={() => setScreen("record")}
      assistiveFeedback={praatMetrics?.assistive_feedback ?? null}
    />
  );
}
