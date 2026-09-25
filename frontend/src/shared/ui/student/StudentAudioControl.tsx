import { useRef, useState } from "react";
import StudentIcon from "./StudentIcon";
import "./StudentAudioControl.css";

interface StudentAudioControlProps {
  audioUrl?: string;
  label: string;
  compact?: boolean;
  showDuration?: boolean;
}

/**
 * Plays only a real recorded/imported model clip. Missing audio is explicit
 * so content owners can identify records that still need an audio update.
 */
export default function StudentAudioControl({ audioUrl, label, compact = false, showDuration = false }: StudentAudioControlProps) {
  const [playing, setPlaying] = useState(false);
  const [duration, setDuration] = useState<number | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const available = Boolean(audioUrl?.trim());
  const displayLabel = available ? label : "Audio not available";
  const durationLabel = showDuration && duration !== null ? ` (${formatAudioDuration(duration)})` : "";

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
      setPlaying(true);
      void audioRef.current.play().catch(() => setPlaying(false));
    }
  };

  return (
    <button
      type="button"
      className={`sa-audio-control ${compact ? "is-compact" : ""}`}
      onClick={handlePlay}
      disabled={!available}
      aria-label={`${displayLabel}${durationLabel}`}
      aria-pressed={available ? playing : undefined}
    >
      <StudentIcon name={playing ? "graphic_eq" : "play_arrow"} size={compact ? 15 : 18} role="decorative" />
      <span>{displayLabel}{durationLabel}</span>
    </button>
  );
}

function formatAudioDuration(seconds: number): string {
  const rounded = Math.max(0, Math.round(seconds));
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, "0")}`;
}
