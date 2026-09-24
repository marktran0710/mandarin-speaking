import { useRef, useState } from "react";
import StudentIcon from "./StudentIcon";
import "./StudentAudioControl.css";

interface StudentAudioControlProps {
  audioUrl?: string;
  fallbackText?: string;
  label: string;
  compact?: boolean;
}

/**
 * Plays a real recorded/model clip when audioUrl exists; falls back to
 * speechSynthesis for a word/sentence when it doesn't (never silent, never
 * fake — matches the same fallback the legacy vocabulary preview used).
 */
export default function StudentAudioControl({ audioUrl, fallbackText, label, compact = false }: StudentAudioControlProps) {
  const [playing, setPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const handlePlay = () => {
    if (audioUrl) {
      if (!audioRef.current) {
        audioRef.current = new Audio(audioUrl);
        audioRef.current.addEventListener("ended", () => setPlaying(false));
      }
      setPlaying(true);
      void audioRef.current.play().catch(() => setPlaying(false));
      return;
    }
    if (fallbackText && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      const utter = new SpeechSynthesisUtterance(fallbackText);
      utter.lang = "zh-TW";
      utter.onend = () => setPlaying(false);
      setPlaying(true);
      window.speechSynthesis.speak(utter);
    }
  };

  return (
    <button
      type="button"
      className={`sa-audio-control ${compact ? "is-compact" : ""}`}
      onClick={handlePlay}
      aria-pressed={playing}
    >
      <StudentIcon name={playing ? "graphic_eq" : "play_arrow"} size={compact ? 15 : 18} role="decorative" />
      <span>{label}</span>
    </button>
  );
}
