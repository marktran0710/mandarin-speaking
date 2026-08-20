import { useEffect, useId, useState } from "react";
import { BiLabel } from "./BiLabel";

export default function RecordingPlayback({ blob }: { blob: Blob }) {
  const [url, setUrl] = useState<string | null>(null);
  const labelId = useId();

  useEffect(() => {
    const objectUrl = URL.createObjectURL(blob);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [blob]);

  if (!url) return null;

  return (
    <div className="recording-playback">
      <p className="recording-playback-label" id={labelId}>
        <BiLabel k="your_recording" />
      </p>
      <audio
        controls
        src={url}
        className="recording-playback-audio"
        aria-labelledby={labelId}
      />
    </div>
  );
}
