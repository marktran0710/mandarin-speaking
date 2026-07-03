import { useEffect, useMemo, useState } from "react";

interface WordProsody {
  token: string;
  index: number;
  start_time: number;
  end_time: number;
  pitch_contour: Array<[number, number]>;
  reference_contour?: Array<[number, number]>;
  mean_pitch: number;
  pitch_range: number;
  start_pitch: number;
  end_pitch: number;
  contour_shape: string;
  feedback: string;
}

interface PraatTimelineProps {
  audioBlob?: Blob | null;
  pitchContour: Array<[number, number]>;
  wordProsody?: WordProsody[];
  transcription?: string;
}

interface WaveformState {
  duration: number;
  peaks: number[];
}

const SVG_WIDTH = 1000;
const WAVEFORM_HEIGHT = 96;
const PITCH_HEIGHT = 108;
const WORD_TIER_HEIGHT = 70;
const TIMELINE_TOP = 26;
const WAVEFORM_TOP = TIMELINE_TOP;
const PITCH_TOP = WAVEFORM_TOP + WAVEFORM_HEIGHT + 18;
const WORD_TOP = PITCH_TOP + PITCH_HEIGHT + 18;
const SVG_HEIGHT = WORD_TOP + WORD_TIER_HEIGHT + 34;

export default function PraatTimeline({
  audioBlob,
  pitchContour,
  wordProsody = [],
  transcription = "",
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
    () => buildReferencePaths(words, timelineDuration, pitchRange.min, pitchRange.max),
    [words, timelineDuration, pitchRange],
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

function TimelineGrid({ duration }: { duration: number }) {
  const tickCount = Math.min(8, Math.max(3, Math.ceil(duration)));

  return (
    <>
      {Array.from({ length: tickCount + 1 }, (_, index) => {
        const ratio = index / tickCount;
        const x = 92 + ratio * 880;
        const label = `${(ratio * duration).toFixed(1)}s`;

        return (
          <g key={label}>
            <line
              x1={x}
              x2={x}
              y1={WAVEFORM_TOP}
              y2={WORD_TOP + WORD_TIER_HEIGHT}
              stroke="#dfe5ee"
              strokeDasharray="5 7"
            />
            <text x={x + 4} y={SVG_HEIGHT - 12} className="praat-axis-label">
              {label}
            </text>
          </g>
        );
      })}
    </>
  );
}

function WaveformBars({ peaks }: { peaks: number[] }) {
  const maxPeak = Math.max(...peaks, 0.01);
  const barWidth = 880 / peaks.length;
  const centerY = WAVEFORM_TOP + WAVEFORM_HEIGHT / 2;

  return (
    <>
      <line x1="92" x2="972" y1={centerY} y2={centerY} stroke="#9aa7b5" />
      {peaks.map((peak, index) => {
        const normalized = peak / maxPeak;
        const height = Math.max(2, normalized * (WAVEFORM_HEIGHT - 16));
        const x = 92 + index * barWidth;

        return (
          <rect
            key={`${peak}-${index}`}
            x={x}
            y={centerY - height / 2}
            width={Math.max(1, barWidth * 0.76)}
            height={height}
            rx="1"
            fill="#222831"
            opacity="0.78"
          />
        );
      })}
    </>
  );
}

function WordSegment({
  word,
  duration,
  highlighted,
}: {
  word: WordProsody;
  duration: number;
  highlighted: boolean;
}) {
  const x = 92 + (word.start_time / duration) * 880;
  const endX = 92 + (word.end_time / duration) * 880;
  const width = Math.max(32, endX - x);

  return (
    <g>
      <rect
        x={x}
        y={WORD_TOP}
        width={width}
        height={WORD_TIER_HEIGHT}
        fill={highlighted ? "#ffe66d" : "#ffffff"}
        stroke="#5967d8"
        strokeWidth="2"
      />
      <text
        x={x + width / 2}
        y={WORD_TOP + 28}
        className="praat-word-label"
        textAnchor="middle"
      >
        {word.token}
      </text>
      <text
        x={x + width / 2}
        y={WORD_TOP + 48}
        className="praat-word-detail"
        textAnchor="middle"
      >
        {word.mean_pitch > 0
          ? `${Math.round(word.mean_pitch)}Hz ${word.contour_shape}`
          : word.contour_shape}
      </text>
    </g>
  );
}

function timeToX(time: number, duration: number): number {
  return 92 + (time / duration) * 880;
}

function pitchToY(frequency: number, minPitch: number, maxPitch: number): number {
  const pitchRange = Math.max(maxPitch - minPitch, 1);
  return (
    PITCH_TOP + PITCH_HEIGHT - 12 - ((frequency - minPitch) / pitchRange) * (PITCH_HEIGHT - 24)
  );
}

function buildPitchPath(
  pitchContour: Array<[number, number]>,
  duration: number,
): string {
  if (pitchContour.length < 2) {
    return "";
  }

  const frequencies = pitchContour.map((point) => point[1]);
  const minPitch = Math.min(...frequencies);
  const maxPitch = Math.max(...frequencies);

  return pitchContour
    .map(([time, frequency], index) => {
      const x = timeToX(time, duration);
      const y = pitchToY(frequency, minPitch, maxPitch);
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

/** Per-word dashed target-shape overlay, mapped onto the same y-scale as the
 * whole-sentence actual pitch line (pitchRange.min/max) so the two are
 * directly comparable rather than each auto-scaling to its own range. */
function buildReferencePaths(
  wordProsody: WordProsody[],
  duration: number,
  minPitch: number,
  maxPitch: number,
): Array<{ key: string; d: string }> {
  return wordProsody
    .filter((word) => (word.reference_contour?.length ?? 0) > 1)
    .map((word) => ({
      key: `ref-${word.token}-${word.index}`,
      d: (word.reference_contour as Array<[number, number]>)
        .map(([time, frequency], index) => {
          const x = timeToX(time, duration);
          const y = pitchToY(frequency, minPitch, maxPitch);
          return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
        })
        .join(" "),
    }));
}

function fallbackWordSegments(
  transcription: string,
  duration: number,
): WordProsody[] {
  const tokens =
    transcription.match(/[\u4e00-\u9fff]|[A-Za-z0-9']+/g)?.slice(0, 40) || [];

  if (tokens.length === 0) {
    return [];
  }

  const segmentDuration = duration / tokens.length;
  return tokens.map((token, index) => ({
    token,
    index,
    start_time: index * segmentDuration,
    end_time: index === tokens.length - 1 ? duration : (index + 1) * segmentDuration,
    pitch_contour: [],
    mean_pitch: 0,
    pitch_range: 0,
    start_pitch: 0,
    end_pitch: 0,
    contour_shape: "variable",
    feedback: "",
  }));
}
