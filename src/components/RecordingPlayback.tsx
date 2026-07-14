import { useEffect, useState } from "react";
import { BiLabel } from "./BiLabel";

export default function RecordingPlayback({ blob }: { blob: Blob }) {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    const objectUrl = URL.createObjectURL(blob);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [blob]);

  if (!url) return null;

  return (
    <div className="recording-playback">
      <p className="recording-playback-label">
        <BiLabel k="your_recording" />
      </p>
      <audio controls src={url} className="recording-playback-audio" />
    </div>
  );
}
