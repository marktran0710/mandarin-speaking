import { useEffect, useRef, useState } from "react";
import StudentIcon from "./StudentIcon";
import "./ScenePracticeWord.css";

/**
 * A single, low-friction action for a scene vocabulary row.
 *
 * Word recording used to live here as a second pronunciation workflow. That
 * duplicated the full-sentence recorder and made the study table noisy. The
 * Speaking results flow is now the one place where students record and get
 * feedback; this row only lets them listen to the teacher/model clip.
 */
export default function ScenePracticeWord({
  word,
  audioUrl,
}: {
  word: string;
  /** Model-voice clip aligned to this vocabulary word, when available. */
  audioUrl?: string;
}) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const canUseSpeechSynthesis =
    typeof window !== "undefined" &&
    "speechSynthesis" in window &&
    "SpeechSynthesisUtterance" in window;

  useEffect(() => {
    const audio = audioRef.current;
    if (audio && !audio.paused) audio.pause();
    if (audio) audio.currentTime = 0;
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    setIsPlaying(false);

    return () => {
      if (audio && !audio.paused) audio.pause();
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, [audioUrl]);

  const togglePlayback = () => {
    const audio = audioRef.current;
    if (!audioUrl) {
      if (!canUseSpeechSynthesis) return;
      if (isPlaying) {
        window.speechSynthesis.cancel();
        setIsPlaying(false);
        return;
      }

      const utterance = new SpeechSynthesisUtterance(word);
      utterance.lang = "zh-TW";
      utterance.onend = () => setIsPlaying(false);
      utterance.onerror = () => setIsPlaying(false);
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(utterance);
      setIsPlaying(true);
      return;
    }
    if (!audio) return;

    if (!audio.paused) {
      audio.pause();
      audio.currentTime = 0;
      setIsPlaying(false);
      return;
    }

    audio.currentTime = 0;
    void audio.play().catch(() => {
      // Browsers can reject playback when the media URL is unavailable. Keep
      // the row quiet; the main practice flow still remains usable.
      setIsPlaying(false);
    });
  };

  return (
    <>
      {audioUrl && (
        <audio
          ref={audioRef}
          className="scene-practice-audio"
          src={audioUrl}
          preload="metadata"
          onPlay={() => setIsPlaying(true)}
          onPause={() => setIsPlaying(false)}
          onEnded={() => setIsPlaying(false)}
          aria-hidden="true"
        />
      )}
      <button
        type="button"
        className={`scene-practice-listen${isPlaying ? " playing" : ""}`}
        onClick={togglePlayback}
        disabled={!audioUrl && !canUseSpeechSynthesis}
        aria-label={`${isPlaying ? "Stop" : "Listen to"} the model pronunciation of ${word}`}
        title="Listen to this word"
      >
        <StudentIcon name={isPlaying ? "pause" : "volume"} size={17} aria-hidden="true" />
      </button>
    </>
  );
}
