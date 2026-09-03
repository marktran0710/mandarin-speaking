import { BiLabel } from "./BiLabel";
import Icon from "../shared/ui/Icon";
import "./ReferenceAudioCard.css";

interface ReferenceAudioCardProps {
  audioUrl?: string;
  sentence?: string;
}

export default function ReferenceAudioCard({ audioUrl, sentence }: ReferenceAudioCardProps) {
  const hasAudio = Boolean(audioUrl?.trim());
  return (
    <section className="reference-audio-card" aria-label="Model recording">
      <div className="reference-audio-card-heading">
        <span className="reference-audio-card-icon"><Icon name="microphone" size={18} /></span>
        <div>
          <p className="reference-audio-card-title"><BiLabel zh="示範音檔" en="Model" /></p>
          <p className="reference-audio-card-hint"><BiLabel zh="先聽，再跟讀" en="Listen and repeat" /></p>
        </div>
      </div>
      {sentence && <p className="reference-audio-card-sentence" lang="zh-TW">{sentence}</p>}
      {hasAudio ? (
        <audio className="reference-audio-card-player" controls preload="metadata" src={audioUrl} aria-label={`Model recording: ${sentence || "scene sentence"}`} />
      ) : (
        <p className="reference-audio-card-unavailable" role="status"><BiLabel zh="暫無示範音檔" en="Audio unavailable" /></p>
      )}
    </section>
  );
}
