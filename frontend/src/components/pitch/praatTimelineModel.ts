export interface WordProsody {
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


export const SVG_WIDTH = 1000;
export const WAVEFORM_HEIGHT = 96;
export const PITCH_HEIGHT = 108;
export const WORD_TIER_HEIGHT = 70;
const TIMELINE_TOP = 26;
export const WAVEFORM_TOP = TIMELINE_TOP;
export const PITCH_TOP = WAVEFORM_TOP + WAVEFORM_HEIGHT + 18;
export const WORD_TOP = PITCH_TOP + PITCH_HEIGHT + 18;
export const SVG_HEIGHT = WORD_TOP + WORD_TIER_HEIGHT + 34;


function timeToX(time: number, duration: number): number {
  return 92 + (time / duration) * 880;
}

function pitchToY(frequency: number, minPitch: number, maxPitch: number): number {
  const pitchRange = Math.max(maxPitch - minPitch, 1);
  return (
    PITCH_TOP + PITCH_HEIGHT - 12 - ((frequency - minPitch) / pitchRange) * (PITCH_HEIGHT - 24)
  );
}

/** Draws a Hz-over-time line. `minPitch`/`maxPitch` default to the line's
 * own range; pass a shared range when several lines must be comparable. */
export function buildPitchPath(
  pitchContour: Array<[number, number]>,
  duration: number,
  minPitch?: number,
  maxPitch?: number,
): string {
  if (pitchContour.length < 2) {
    return "";
  }

  const frequencies = pitchContour.map((point) => point[1]);
  const low = minPitch ?? Math.min(...frequencies);
  const high = maxPitch ?? Math.max(...frequencies);

  return pitchContour
    .map(([time, frequency], index) => {
      const x = timeToX(time, duration);
      const y = pitchToY(frequency, low, high);
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

export function fallbackWordSegments(
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
