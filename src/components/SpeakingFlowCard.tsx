import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { BiLabel } from "./BiLabel";
import AppButton from "./AppButton";
import SpeakingResultsFlow from "./SpeakingResultsFlow";
import { sceneReady } from "../utils/storyRecorderFeedback";
import type { SelfEvalLevel } from "../utils/selfEvalComparison";
import type {
  PraatMetrics,
  SpeechModel,
  Topic,
} from "./StoryRecorder";
import ModelRecordingPractice from "./ModelRecordingPractice";
import "./SpeakingFlowCard.css";

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
  narrativeMode: Topic["narrativeMode"];
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
  submittedAudioName: string;
  selectedModel: SpeechModel;
  groqAvailable: boolean;
  onSelectedModelChange: (model: SpeechModel) => void;
  recordingButtonDisabled: boolean;
  onPrimaryRecordingAction: () => void;
  onSubmitVoiceFile: (event: ChangeEvent<HTMLInputElement>) => void;
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
  narrativeMode,
  prog,
  praatMetrics,
  analysisAudioBlob,
  error,
  isRecording,
  isBusy,
  isTranscribing,
  isAnalyzing,
  recordingDuration,
  silenceDuration,
  submittedAudioName,
  selectedModel,
  groqAvailable,
  onSelectedModelChange,
  recordingButtonDisabled,
  onPrimaryRecordingAction,
  onSubmitVoiceFile,
  masteryPassed,
  contentPassed,
  clearedWords,
  onWordDrillPass,
  onSelfEvalSubmit,
  hasNextScene,
  onNextScene,
  onViewSummary,
}: SpeakingFlowCardProps) {
  const [screen, setScreen] = useState<"record" | "results">("record");
  const uploadInputRef = useRef<HTMLInputElement>(null);

  // Flip to results exactly when an analysis finishes (busy → idle with
  // fresh metrics) — not merely "metrics exist", which would trap the
  // student on the results screen after choosing to record again.
  const wasBusy = useRef(false);
  useEffect(() => {
    if (wasBusy.current && !isBusy && praatMetrics) {
      setScreen("results");
    }
    wasBusy.current = isBusy;
  }, [isBusy, praatMetrics]);

  // Switching scenes shows that scene's last result if it has one (praatMetrics
  // is already cached per scene by the parent), instead of always dropping
  // back to the record screen and losing the student's earlier attempt.
  useEffect(() => {
    setScreen(praatMetrics ? "results" : "record");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedImageIndex]);

  const attempts = prog?.attempts ?? 0;
  // Mastery (every word passed its per-syllable verdict on a full-sentence
  // recording) gates progression alongside the score/attempts unlock — the
  // attempts escape hatch never bypasses failing words.
  const ready =
    (prog ? sceneReady(prog) : false) && masteryPassed && contentPassed;

  const sceneChip = (
    <span className="sfc-scene-chip">
      <BiLabel
        zh={`部分 ${selectedImageIndex + 1}/${totalScenes}`}
        en={`Scene ${selectedImageIndex + 1} of ${totalScenes}`}
      />
      {attempts > 0 && (
        <span className="sfc-attempt-chip">
          <BiLabel
            zh={`第 ${attempts} 次`}
            en={`Attempt ${attempts}`}
          />
        </span>
      )}
    </span>
  );

  // ── Analyzing overlay (either screen) ─────────────────────────────────
  if (isTranscribing || isAnalyzing) {
    return (
      <section className="speaking-flow-card sfc-analyzing" aria-label="Analyzing recording">
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
            <span className="loading-step-arrow">→</span>
            <span className={`loading-step ${isAnalyzing && !isTranscribing ? "active" : ""}`}>
              Praat
            </span>
            <span className="loading-step-arrow">→</span>
            <span className="loading-step">
              <BiLabel k="feedback" />
            </span>
          </div>
        </div>
      </section>
    );
  }

  // ── Screen 1: record ──────────────────────────────────────────────────
  if (screen === "record" || !praatMetrics) {
    return (
      <section className="speaking-flow-card sfc-screen" aria-label="Record your story">
        <div className="practice-workspace">
        <div className="practice-scene-col">
          <div className="practice-scene-image">
            <img src={selectedImage} alt={`Scene ${selectedImageIndex + 1}`} />
          </div>
          {sceneChip}
        </div>

        <div className="sfc-record-main">
        <ModelRecordingPractice
          sceneIndex={selectedImageIndex}
          modelSentence={modelSentence}
          modelAudioUrl={modelAudioUrl}
        />

        <div className="sfc-record-panel">
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
                  <option value="webspeech">Browser Speech — free fallback</option>
                  <option value="ctwhisper">Chinese/Taiwanese Whisper — local</option>
                  <option value="vibevoice">VibeVoice — experimental local</option>
                </select>
              </label>
              <p className="sfc-speech-source-note">
                {selectedModel === "groq"
                  ? "Recommended: fast, stable Mandarin transcription through the configured free API tier."
                  : selectedModel === "webspeech"
                    ? "Uses the browser's live speech service; availability depends on the browser and network."
                    : selectedModel === "ctwhisper"
                      ? "Runs the local Chinese/Taiwanese Whisper model; private but slower on CPU."
                      : "Experimental local model; its first run may take several minutes to load."}
              </p>
            </details>
            <div className="sfc-action-intro">
              <span className="sfc-action-step" aria-hidden="true">1</span>
              <div>
                <p className="sfc-action-title"><BiLabel k="speaking" /></p>
                <p className="sfc-action-note"><BiLabel k="record" /></p>
              </div>
            </div>
            <AppButton
              tone={isRecording ? "danger" : "primary"}
              size="lg"
              onClick={onPrimaryRecordingAction}
              disabled={recordingButtonDisabled}
              className={`sfc-record-btn${isRecording ? " is-recording" : ""}`}
              aria-pressed={isRecording}
            >
              <span className="sfc-record-icon" aria-hidden="true">
                {isRecording ? "■" : "●"}
              </span>
              {isRecording ? (
                <BiLabel k="stop_recording" />
              ) : (
                <BiLabel k="record" />
              )}
            </AppButton>
            {isRecording && (
              <div className="practice-timer" aria-live="polite">
                <span>{recordingDuration}s</span>
                {selectedModel === "webspeech" && (
                  <span className="practice-silence">
                    <BiLabel
                      zh={`靜音 ${silenceDuration}s / 7s`}
                      pinyin={`Jìngyīn ${silenceDuration}s / 7s`}
                      en={`silence ${silenceDuration}s / 7s`}
                    />
                  </span>
                )}
              </div>
            )}

            <div className="sfc-secondary-actions">
              <AppButton
                tone="subtle"
                size="sm"
                className="sfc-upload-btn"
                onClick={() => uploadInputRef.current?.click()}
                disabled={isBusy}
              >
                <span aria-hidden="true">↥</span>
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
            {submittedAudioName && (
              <p className="submitted-audio-name">✓ {submittedAudioName}</p>
            )}
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
      narrativeMode={narrativeMode}
      attempts={attempts}
      ready={ready}
      masteryPassed={masteryPassed}
      praatMetrics={praatMetrics}
      analysisAudioBlob={analysisAudioBlob}
      submittedAudioName={submittedAudioName}
      clearedWords={clearedWords}
      onWordDrillPass={onWordDrillPass}
      onSelfEvalSubmit={onSelfEvalSubmit}
      hasNextScene={hasNextScene}
      onNextScene={onNextScene}
      onViewSummary={onViewSummary}
      onRecordAgain={() => setScreen("record")}
    />
  );
}
