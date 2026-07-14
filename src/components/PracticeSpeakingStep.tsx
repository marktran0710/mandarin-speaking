import type { ChangeEvent } from "react";
import { BiLabel, BiText } from "./BiLabel";
import type {
  AiProviderOption,
  PraatMetrics,
  SpeechModel,
  TranscriptionItem,
} from "./StoryRecorder";

interface PracticeSpeakingStepProps {
  aiProviders: AiProviderOption[];
  aiProvider: string;
  onAiProviderChange: (value: string) => void;
  selectedModel: SpeechModel;
  onSelectedModelChange: (value: SpeechModel) => void;
  silenceDuration: number;
  recordingDuration: number;
  submittedAudioName: string;
  praatMetrics: PraatMetrics | null;
  transcriptions: TranscriptionItem[];
  isRecording: boolean;
  isBusy: boolean;
  recordingButtonDisabled: boolean;
  onPrimaryRecordingAction: () => void;
  onSubmitVoiceFile: (event: ChangeEvent<HTMLInputElement>) => void;
}

export default function PracticeSpeakingStep({
  aiProviders,
  aiProvider,
  onAiProviderChange,
  selectedModel,
  onSelectedModelChange,
  silenceDuration,
  recordingDuration,
  submittedAudioName,
  praatMetrics,
  transcriptions,
  isRecording,
  isBusy,
  recordingButtonDisabled,
  onPrimaryRecordingAction,
  onSubmitVoiceFile,
}: PracticeSpeakingStepProps) {
  return (
    <>
      <div className="practice-guide-header">
        <span>🎙️</span>
        <div>
          <h3>
            <BiLabel k="record_your_story" />
          </h3>
        </div>
      </div>

      <div className="practice-record-area">
        {aiProviders.length > 0 && (
          <div
            className="record-engine-switch"
            role="group"
            aria-label="AI feedback engine"
          >
            <label
              className="record-engine-switch-label"
              htmlFor="ai-engine-select"
            >
              <BiLabel k="ai_engine" />
            </label>
            <select
              id="ai-engine-select"
              className="record-engine-switch-options"
              value={aiProvider}
              onChange={(e) => {
                const next = e.target.value;
                onAiProviderChange(next);
                // Groq handles Whisper transcription as well as feedback,
                // so align the speech source automatically.
                if (next === "groq") onSelectedModelChange("groq");
              }}
              disabled={isBusy}
            >
              {aiProviders.map((p) => (
                <option
                  key={p.id}
                  value={p.id}
                  disabled={!p.available || p.id === "local"}
                >
                  {p.label}
                  {p.available && p.id !== "local" ? "" : " 🔒"}
                </option>
              ))}
            </select>
          </div>
        )}
        <button
          type="button"
          onClick={onPrimaryRecordingAction}
          disabled={recordingButtonDisabled}
          className={`btn-practice-record${isRecording ? " is-recording" : ""}`}
        >
          {isRecording ? (
            <BiLabel k="stop_recording" />
          ) : (
            <BiLabel k="record" />
          )}
        </button>
        {isRecording && (
          <div className="practice-timer">
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
        <label
          className={`btn-practice-upload${isBusy ? " disabled" : ""}`}
          role="button"
          tabIndex={isBusy ? -1 : 0}
        >
          <BiLabel k="upload_audio" />
          <input
            className="submit-voice-input"
            type="file"
            accept="audio/*,.wav,.wave,.webm,.mp3,.m4a,.ogg"
            onChange={onSubmitVoiceFile}
            disabled={isBusy}
          />
        </label>
        {submittedAudioName && (
          <p className="submitted-audio-name">✓ {submittedAudioName}</p>
        )}
      </div>

      <div className="transcriptions">
        <h2>
          <BiLabel k="speech_transcript" />
        </h2>
        {praatMetrics?.transcription && (
          <div className="transcription-item transcription-asr-primary">
            <div className="item-header">
              <span className="time">
                <BiLabel k="asr_result" />
              </span>
              <span className="model-badge">
                {(praatMetrics.transcription_model || "ASR").toUpperCase()}
              </span>
            </div>
            <p lang="zh-TW">{praatMetrics.transcription}</p>
          </div>
        )}
        {transcriptions.length === 0 && !praatMetrics?.transcription ? (
          <p className="empty">
            <BiText k="your_transcript_will_appear_after_record" />
          </p>
        ) : (
          <div className="transcriptions-scroll">
            {transcriptions.map((item) => (
              <div
                key={`${item.timestamp}-${item.text}`}
                className="transcription-item"
              >
                <div className="item-header">
                  <span className="time">{item.timestamp}</span>
                  <span className="model-badge">
                    {item.model.toUpperCase()}
                  </span>
                </div>
                <p>{item.text}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      <details className="practice-model-picker">
        <summary>
          <BiLabel k="recording_options" />
        </summary>
        <label className="practice-model-label" htmlFor="speech-source">
          <BiLabel k="speech_source" />
        </label>
        <select
          id="speech-source"
          value={selectedModel}
          onChange={(e) =>
            onSelectedModelChange(e.target.value as SpeechModel)
          }
          disabled={isBusy}
        >
          <option value="webspeech">
            瀏覽器（繁體中文） Browser (Traditional Chinese)
          </option>
          <option value="groq">
            Groq Whisper（免費，雲端） Groq Whisper (free, cloud)
          </option>
          <option value="ctwhisper">
            Whisper（中文／台語，本地） Whisper (Chinese / Taiwanese, local)
          </option>
          <option value="vibevoice">
            VibeVoice-ASR（本地檔案） VibeVoice-ASR (local file)
          </option>
        </select>
      </details>
    </>
  );
}
