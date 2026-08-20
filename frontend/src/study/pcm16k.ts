/**
 * STUDY_PCM16K_v1 — the one sample-rate conversion used by the study path.
 *
 * The frozen tone model was fitted only on natively-16 kHz audio, and Phase TV2
 * measured that resampling can move a short-token score across the PASS
 * threshold. So the study path converts exactly once, here, in the browser; the
 * backend receives 16 kHz and resamples nothing.
 *
 * This is the TypeScript mirror of
 * backend/pronunciation/wav2vec_tone/study_pcm16k.py. Both implement the spec
 * below, and verify_human_exposure_path.py asserts the two agree to 1e-12 on
 * shared vectors — "one deterministic implementation" is checked, not claimed.
 *
 *   STUDY_PCM16K_v1
 *     target rate    16000 Hz, mono, 16-bit signed PCM in a WAV container
 *     identity rule  source rate === 16000 → samples pass through untouched
 *     ratio          L/M reduced by gcd(16000, sourceRate)
 *     filter         Blackman-windowed sinc, linear phase
 *     cutoff         0.5 / max(L, M)   (normalised to the upsampled rate)
 *     taps           2 * (16 * max(L, M)) + 1
 *     gain           L
 *     evaluation     polyphase; only non-zero upsampled taps are touched
 *     edges          source index clamped to [0, n-1] (constant extension)
 *
 * Blackman rather than Kaiser deliberately: no modified Bessel function is
 * needed, so the two implementations cannot drift through a different I0
 * approximation.
 */

export const STUDY_PCM_SPEC_VERSION = "STUDY_PCM16K_v1";
export const TARGET_SAMPLE_RATE = 16000;
const HALF_TAPS_PER_PHASE = 16;
const PCM_FULL_SCALE = 32767;

export interface StudyAudioMetadata {
  pcm_spec_version: string;
  capture_sample_rate: number;
  output_sample_rate: number;
  conversion: "identity" | "blackman_sinc_polyphase";
  input_frames: number;
  output_frames: number;
  input_duration_ms: number;
  output_duration_ms: number;
}

function greatestCommonDivisor(a: number, b: number): number {
  let x = Math.abs(a);
  let y = Math.abs(b);
  while (y) {
    [x, y] = [y, x % y];
  }
  return x;
}

/** Blackman-windowed sinc low-pass, scaled by the upsampling factor. */
export function designFilter(up: number, down: number): Float64Array {
  const maxRate = Math.max(up, down);
  const half = HALF_TAPS_PER_PHASE * maxRate;
  const taps = 2 * half + 1;
  const cutoff = 0.5 / maxRate;
  const coefficients = new Float64Array(taps);
  for (let index = 0; index < taps; index += 1) {
    const position = index - half;
    let value: number;
    if (position === 0) {
      value = 2.0 * cutoff;
    } else {
      const angle = Math.PI * position;
      value = Math.sin(2.0 * cutoff * angle) / angle;
    }
    const ratio = index / (taps - 1);
    const window =
      0.42 -
      0.5 * Math.cos(2.0 * Math.PI * ratio) +
      0.08 * Math.cos(4.0 * Math.PI * ratio);
    coefficients[index] = value * window * up;
  }
  return coefficients;
}

/** Convert float samples at `sourceRate` to 16 kHz using STUDY_PCM16K_v1. */
export function resampleTo16k(
  samples: Float32Array | Float64Array | number[],
  sourceRate: number,
): Float64Array {
  const input = Float64Array.from(samples as ArrayLike<number>);
  if (sourceRate === TARGET_SAMPLE_RATE) {
    // Identity rule: never filter audio that is already on contract.
    return input;
  }
  if (!Number.isFinite(sourceRate) || sourceRate <= 0) {
    throw new Error(`invalid source rate ${sourceRate}`);
  }

  const divisor = greatestCommonDivisor(TARGET_SAMPLE_RATE, Math.round(sourceRate));
  const up = TARGET_SAMPLE_RATE / divisor;
  const down = Math.round(sourceRate) / divisor;
  const coefficients = designFilter(up, down);
  const taps = coefficients.length;
  const half = (taps - 1) / 2;

  const nIn = input.length;
  if (nIn === 0) {
    return new Float64Array(0);
  }
  const nOut = Math.ceil((nIn * up) / down);
  const output = new Float64Array(nOut);

  for (let n = 0; n < nOut; n += 1) {
    const centre = n * down + half;
    const first = Math.ceil((centre - (taps - 1)) / up);
    const last = Math.floor(centre / up);
    let total = 0.0;
    for (let j = first; j <= last; j += 1) {
      const tap = centre - j * up;
      if (tap < 0 || tap >= taps) continue;
      const sourceIndex = Math.min(Math.max(j, 0), nIn - 1);
      total += input[sourceIndex] * coefficients[tap];
    }
    output[n] = total;
  }
  return output;
}

/** Clamp to [-1, 1] and quantise to signed 16-bit, round-half-away-from-zero. */
export function toPcm16(samples: Float64Array | Float32Array | number[]): Int16Array {
  const input = Float64Array.from(samples as ArrayLike<number>);
  const output = new Int16Array(input.length);
  for (let index = 0; index < input.length; index += 1) {
    const clipped = Math.min(1.0, Math.max(-1.0, input[index]));
    const scaled = clipped * PCM_FULL_SCALE;
    output[index] = scaled >= 0 ? Math.floor(scaled + 0.5) : Math.ceil(scaled - 0.5);
  }
  return output;
}

/** Minimal canonical 16-bit mono WAV, byte-for-byte reproducible. */
export function encodeWav(
  pcm16: Int16Array,
  sampleRate: number = TARGET_SAMPLE_RATE,
): ArrayBuffer {
  const buffer = new ArrayBuffer(44 + pcm16.length * 2);
  const view = new DataView(buffer);
  const ascii = (offset: number, text: string) => {
    for (let index = 0; index < text.length; index += 1) {
      view.setUint8(offset + index, text.charCodeAt(index));
    }
  };
  ascii(0, "RIFF");
  view.setUint32(4, 36 + pcm16.length * 2, true);
  ascii(8, "WAVE");
  ascii(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  ascii(36, "data");
  view.setUint32(40, pcm16.length * 2, true);
  for (let index = 0; index < pcm16.length; index += 1) {
    view.setInt16(44 + index * 2, pcm16[index], true);
  }
  return buffer;
}

/** The complete study conversion, with the metadata the contract requires. */
export function buildStudyWav(
  samples: Float32Array | Float64Array | number[],
  sourceRate: number,
): { blob: Blob; buffer: ArrayBuffer; metadata: StudyAudioMetadata } {
  const inputLength = (samples as ArrayLike<number>).length;
  const converted = resampleTo16k(samples, sourceRate);
  const pcm = toPcm16(converted);
  const buffer = encodeWav(pcm);
  return {
    blob: new Blob([buffer], { type: "audio/wav" }),
    buffer,
    metadata: {
      pcm_spec_version: STUDY_PCM_SPEC_VERSION,
      capture_sample_rate: sourceRate,
      output_sample_rate: TARGET_SAMPLE_RATE,
      conversion:
        sourceRate === TARGET_SAMPLE_RATE ? "identity" : "blackman_sinc_polyphase",
      input_frames: inputLength,
      output_frames: pcm.length,
      input_duration_ms: (inputLength / sourceRate) * 1000,
      output_duration_ms: (pcm.length / TARGET_SAMPLE_RATE) * 1000,
    },
  };
}
