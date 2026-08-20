import type { ChangeEvent, ReactNode } from "react";
import StudentIcon, { type StudentIconName } from "./StudentIcon";
import "./StudentAudioActionPanel.css";

interface StudentAudioActionPanelProps {
  className: string;
  primaryLabel: ReactNode;
  primaryIcon?: StudentIconName;
  uploadLabel: ReactNode;
  status: ReactNode;
  onPrimaryAction: () => void;
  onFileChange: (event: ChangeEvent<HTMLInputElement>) => void;
  accept?: string;
  isRecording: boolean;
  isAnalyzing: boolean;
  hasPendingAudio: boolean;
  pendingAudioName?: string;
  audioUrl?: string;
  onAnalyze?: () => void;
  analyzeLabel?: ReactNode;
  readyMessage?: ReactNode;
  error?: ReactNode;
  primaryDisabled?: boolean;
  uploadDisabled?: boolean;
  previewClassName?: string;
}

/**
 * The one audio hand-off surface shared by all student speaking exercises.
 * A student always sees the same order: record/upload, review, analyze.
 */
export default function StudentAudioActionPanel({
  className,
  primaryLabel,
  primaryIcon,
  uploadLabel,
  status,
  onPrimaryAction,
  onFileChange,
  accept = "audio/*",
  isRecording,
  isAnalyzing,
  hasPendingAudio,
  pendingAudioName,
  audioUrl,
  onAnalyze,
  analyzeLabel = <span>Analyze this audio</span>,
  readyMessage = <span>Audio ready — review it, then analyze</span>,
  error,
  primaryDisabled = false,
  uploadDisabled = false,
  previewClassName = "student-audio-preview",
}: StudentAudioActionPanelProps) {
  return (
    <div className={`${className} student-audio-action-panel`.trim()}>
      <div className="student-audio-actions" aria-label="Audio actions">
        <button
          type="button"
          className={`btn student-action-record ${isRecording ? "btn-danger" : "btn-primary"}`}
          onClick={onPrimaryAction}
          disabled={isAnalyzing || primaryDisabled}
          aria-pressed={isRecording}
        >
          <StudentIcon name={isRecording ? "stop" : primaryIcon ?? "record"} size={19} />
          {primaryLabel}
        </button>
        <label className="student-action-upload btn btn-secondary">
          <StudentIcon name="upload" size={18} />
          {uploadLabel}
          <input
            type="file"
            accept={accept}
            onChange={onFileChange}
            disabled={isRecording || isAnalyzing || uploadDisabled}
          />
        </label>
        {hasPendingAudio && !isAnalyzing && onAnalyze && (
          <button type="button" className="btn student-action-analyze btn-secondary" onClick={onAnalyze}>
            <StudentIcon name="analyze" size={18} />
            {analyzeLabel}
          </button>
        )}
      </div>
      <p className="student-audio-status">{status}</p>
      {hasPendingAudio && !isAnalyzing && <p className="student-audio-ready">{readyMessage}</p>}
      {pendingAudioName && <p className="student-audio-name">{pendingAudioName}</p>}
      {audioUrl && <audio controls src={audioUrl} className={previewClassName} />}
      {error && <p className="student-audio-error">{error}</p>}
    </div>
  );
}
