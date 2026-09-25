import { SVG_HEIGHT, WAVEFORM_HEIGHT, WAVEFORM_TOP, WORD_TIER_HEIGHT, WORD_TOP, type WordProsody } from "./praatTimelineModel";

export function TimelineGrid({ duration }: { duration: number }) {
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

export function WaveformBars({ peaks }: { peaks: number[] }) {
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

export function WordSegment({
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
      <text x={x + width / 2} y={WORD_TOP + 28} className="praat-word-label" textAnchor="middle">
        {word.token}
      </text>
      <text x={x + width / 2} y={WORD_TOP + 48} className="praat-word-detail" textAnchor="middle">
        {word.mean_pitch > 0 ? `${Math.round(word.mean_pitch)}Hz ${word.contour_shape}` : word.contour_shape}
      </text>
    </g>
  );
}
