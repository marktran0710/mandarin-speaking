import { useEffect, useMemo, useState } from "react";
import { buildPitchPath, buildReferencePaths, fallbackWordSegments, PITCH_HEIGHT, PITCH_TOP, SVG_HEIGHT, SVG_WIDTH, WAVEFORM_HEIGHT, WAVEFORM_TOP, WORD_TIER_HEIGHT, WORD_TOP, type WordProsody } from "./praatTimelineModel";
import { TimelineGrid, WaveformBars, WordSegment } from "./praatTimelineLayers";

interface PraatTimelineProps {
  audioBlob?: Blob | null;
  pitchContour: Array<[number, number]>;
  wordProsody?: WordProsody[];
  transcription?: string;
  /** Set to false when this pitch line IS the target shape (e.g. the model
   * recording's own timeline) — drawing a second dashed reference line over
   * a curve that already equals the target is always redundant there.
   * Defaults to true for usages that compare a student's attempt against a
   * target (StoryRecorder, word/phrase drills). */
  showReferenceOverlay?: boolean;
}
interface WaveformState {
  duration: number;
  peaks: number[];
}

export default function PraatTimeline({
  audioBlob,
  pitchContour,
  wordProsody = [],
  transcription = "",
  showReferenceOverlay = true,
}: PraatTimelineProps) {
  const [waveform, setWaveform] = useState<WaveformState | null>(null);
  const [decodeFailed, setDecodeFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const decodeWaveform = async () => {
      if (!audioBlob || audioBlob.size === 0) {
        setWaveform(null);
        return;
      }

      try {
        setDecodeFailed(false);
        const AudioContextClass =
          window.AudioContext || (window as any).webkitAudioContext;
        const audioContext = new AudioContextClass();
        const arrayBuffer = await audioBlob.arrayBuffer();
        const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
        const channel = audioBuffer.getChannelData(0);
        const bucketCount = 240;
        const bucketSize = Math.max(1, Math.floor(channel.length / bucketCount));
        const peaks = Array.from({ length: bucketCount }, (_, bucketIndex) => {
          const start = bucketIndex * bucketSize;
          const end = Math.min(channel.length, start + bucketSize);
          let peak = 0;

          for (let index = start; index < end; index += 1) {
            peak = Math.max(peak, Math.abs(channel[index]));
          }

          return peak;
        });

        await audioContext.close();

        if (!cancelled) {
          setWaveform({
            duration: audioBuffer.duration,
            peaks,
          });
        }
      } catch {
        if (!cancelled) {
          setDecodeFailed(true);
          setWaveform(null);
        }
      }
    };

    decodeWaveform();

    return () => {
      cancelled = true;
    };
  }, [audioBlob]);

  const timelineDuration = useMemo(() => {
    const audioDuration = waveform?.duration || 0;
    const lastPitchPoint = pitchContour[pitchContour.length - 1];
    const lastWord = wordProsody[wordProsody.length - 1];
    const pitchEnd = lastPitchPoint?.[0] || 0;
    const wordEnd = lastWord?.end_time || 0;

    return Math.max(audioDuration, pitchEnd, wordEnd, 1);
  }, [pitchContour, waveform, wordProsody]);

  const words = useMemo(
    () =>
      wordProsody.length > 0
        ? wordProsody
        : fallbackWordSegments(transcription, timelineDuration),
    [timelineDuration, transcription, wordProsody],
  );

  const pitchPath = useMemo(
    () => buildPitchPath(pitchContour, timelineDuration),
    [pitchContour, timelineDuration],
  );

  const pitchRange = useMemo(() => {
    if (pitchContour.length === 0) {
      return { min: 0, max: 0 };
    }

    const frequencies = pitchContour.map((point) => point[1]);
    return {
      min: Math.round(Math.min(...frequencies)),
      max: Math.round(Math.max(...frequencies)),
    };
  }, [pitchContour]);

  // Dashed target-shape overlay per word, on the same y-scale as the actual
  // pitch line above so a visual gap between the two directly shows where a
  // tone's shape diverges from the ideal — the same comparison as the
  // per-character mini charts, but across the whole sentence.
  const referencePaths = useMemo(
    () =>
      showReferenceOverlay
        ? buildReferencePaths(words, timelineDuration, pitchRange.min, pitchRange.max)
        : [],
    [showReferenceOverlay, words, timelineDuration, pitchRange],
  );

  return (
    <div className="praat-timeline-card">
      <div className="praat-timeline-header">
        <div>
          <span>Praat-style timeline</span>
          <strong>Waveform, pitch contour, and word alignment</strong>
        </div>
        <em>{timelineDuration.toFixed(2)}s</em>
      </div>

      <div className="praat-timeline-scroll">
        <svg
          className="praat-timeline"
          role="img"
          aria-label="Praat style waveform, pitch contour, and word timeline"
          viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`}
        >
          <rect width={SVG_WIDTH} height={SVG_HEIGHT} rx="14" fill="#f8fafc" />
          <TimelineGrid duration={timelineDuration} />

          <text x="18" y={WAVEFORM_TOP + 18} className="praat-row-label">
            waveform
          </text>
          <rect
            x="92"
            y={WAVEFORM_TOP}
            width="880"
            height={WAVEFORM_HEIGHT}
            rx="8"
            fill="#ffffff"
            stroke="#d7dde8"
          />
          {waveform ? (
            <WaveformBars peaks={waveform.peaks} />
          ) : (
            <text x="520" y={WAVEFORM_TOP + 54} className="praat-empty-label">
              {decodeFailed ? "Waveform unavailable" : "Waveform appears after recording"}
            </text>
          )}

          <text x="18" y={PITCH_TOP + 18} className="praat-row-label">
            pitch
          </text>
          <rect
            x="92"
            y={PITCH_TOP}
            width="880"
            height={PITCH_HEIGHT}
            rx="8"
            fill="#ffffff"
            stroke="#d7dde8"
          />
          <text x="936" y={PITCH_TOP + 22} className="praat-axis-label">
            {pitchRange.max || "--"} Hz
          </text>
          <text x="942" y={PITCH_TOP + PITCH_HEIGHT - 10} className="praat-axis-label">
            {pitchRange.min || "--"} Hz
          </text>
          {referencePaths.map(({ key, d }) => (
            <path
              key={key}
              d={d}
              fill="none"
              stroke="#9aa7b5"
              strokeWidth="2.5"
              strokeDasharray="5 5"
              opacity="0.8"
            />
          ))}
          {pitchPath && <path d={pitchPath} fill="none" stroke="#167f92" strokeWidth="4" />}
          {referencePaths.length > 0 && (
            <g className="praat-pitch-legend">
              <line x1="800" y1={PITCH_TOP + 14} x2="818" y2={PITCH_TOP + 14} stroke="#167f92" strokeWidth="4" />
              <text x="822" y={PITCH_TOP + 18} className="praat-axis-label">your pitch</text>
              <line
                x1="800"
                y1={PITCH_TOP + 30}
                x2="818"
                y2={PITCH_TOP + 30}
                stroke="#9aa7b5"
                strokeWidth="2.5"
                strokeDasharray="5 5"
              />
              <text x="822" y={PITCH_TOP + 34} className="praat-axis-label">target shape</text>
            </g>
          )}

          <text x="18" y={WORD_TOP + 18} className="praat-row-label">
            words
          </text>
          <rect
            x="92"
            y={WORD_TOP}
            width="880"
            height={WORD_TIER_HEIGHT}
            rx="8"
            fill="#fffef7"
            stroke="#d7dde8"
          />
          {words.map((word, index) => (
            <WordSegment
              key={`${word.token}-${word.index}-${index}`}
              word={word}
              duration={timelineDuration}
              highlighted={index === words.length - 1}
            />
          ))}
        </svg>
      </div>
    </div>
  );
}

