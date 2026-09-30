import { useRef, useState } from "react";
import StudentIcon from "./StudentIcon";
import StudentSystemText from "./StudentSystemText";
import { studentUiCopy, type StudentUiCopyKey } from "../../../i18n/student-ui-copy";
import "./StudentAudioControl.css";

interface StudentAudioControlProps {
  audioUrl?: string;
  label?: string;
  labelKey?: StudentUiCopyKey;
  compact?: boolean;
  showDuration?: boolean;
}

/**
 * Plays only a real recorded/imported model clip. Missing audio is explicit
 * so content owners can identify records that still need an audio update.
 */
export default function StudentAudioControl({ audioUrl, label, labelKey, compact = false, showDuration = false }: StudentAudioControlProps) {
  const [playing, setPlaying] = useState(false);
  const [failed, setFailed] = useState(false);
  const [duration, setDuration] = useState<number | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const available = Boolean(audioUrl?.trim());
  const displayLabel = !available ? "沒有音訊" : failed ? "不能播放" : labelKey ? undefined : label ?? "聆聽";
  const durationLabel = showDuration && duration !== null ? ` (${formatAudioDuration(duration)})` : "";
  const ariaLabel = `${available && !failed && labelKey ? studentUiCopy[labelKey].zh : displayLabel}${durationLabel}`.trim();

  const handlePlay = () => {
    if (!audioUrl?.trim()) return;

    if (audioUrl) {
      if (!audioRef.current) {
        audioRef.current = new Audio(audioUrl);
        audioRef.current.addEventListener("ended", () => setPlaying(false));
        audioRef.current.addEventListener("loadedmetadata", () => {
          if (Number.isFinite(audioRef.current?.duration)) setDuration(audioRef.current!.duration);
        });
      }
      setFailed(false);
      setPlaying(true);
      // A rejected play() (missing file, 403, unsupported format) used to fail
      // silently, leaving a normal-looking button that did nothing. Show it,
      // and drop the element so the next click retries from a fresh request.
      void audioRef.current.play().catch(() => {
        audioRef.current = null;
        setPlaying(false);
        setFailed(true);
      });
    }
  };

  return (
    <button
      type="button"
      className={`sa-audio-control ${compact ? "is-compact" : ""} ${failed ? "is-error" : ""}`}
      onClick={handlePlay}
      disabled={!available}
      aria-label={ariaLabel}
      aria-pressed={available ? playing : undefined}
    >
      <StudentIcon name={playing ? "graphic_eq" : "play_arrow"} size={compact ? 15 : 18} role="decorative" />
      <span>{available && labelKey ? <StudentSystemText k={labelKey} withinControl /> : displayLabel}{durationLabel}</span>
    </button>
  );
}

function formatAudioDuration(seconds: number): string {
  const rounded = Math.max(0, Math.round(seconds));
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, "0")}`;
}
