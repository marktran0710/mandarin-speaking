/** One octave, in semitones. */
export const OCTAVE_SEMITONES = 12;

/** Price of starting or ending an octave-shifted block. A block is only folded
 * back when the jumps around it save more than this, so a real 7-9 semitone
 * reset between two syllables is left alone while a ~12 semitone half/double
 * error (which a pitch tracker can hold for many frames on creaky or breathy
 * voice) is corrected. */
export const OCTAVE_SWITCH_PENALTY = 8;

const OFFSETS = [0, -OCTAVE_SEMITONES, OCTAVE_SEMITONES] as const;

/**
 * Removes half/double-frequency tracker errors from a pitch curve in
 * semitones, however many consecutive frames they last.
 *
 * Each point may be shifted by 0 or +-12 semitones; a Viterbi pass picks the
 * shifts that minimise the total frame-to-frame jump plus
 * `OCTAVE_SWITCH_PENALTY` per shift change. That is what separates the two
 * cases a local-median rule confuses: a lone spike and a long block are both
 * folded when they sit an octave off, while genuine large movements (a tone-4
 * fall, a pitch reset across a syllable boundary) are smaller than an octave
 * and cost less to keep than to fold.
 *
 * Only the shape of the curve matters to the callers, so the absolute level of
 * the result is arbitrary (a fully shifted curve costs a switch penalty and is
 * never preferred).
 */
export function foldOctaveBlocks(values: number[]): number[] {
  const count = values.length;
  if (count < 3) return [...values];

  const cost: number[][] = Array.from({ length: count }, () => [0, 0, 0]);
  const from: number[][] = Array.from({ length: count }, () => [0, 0, 0]);
  OFFSETS.forEach((offset, k) => {
    cost[0][k] = offset === 0 ? 0 : OCTAVE_SWITCH_PENALTY;
  });
  for (let i = 1; i < count; i += 1) {
    for (let k = 0; k < OFFSETS.length; k += 1) {
      let best = Infinity;
      let bestFrom = 0;
      // Try "no shift" first so ties keep the original value.
      for (let j = 0; j < OFFSETS.length; j += 1) {
        const jump = Math.abs(values[i] + OFFSETS[k] - (values[i - 1] + OFFSETS[j]));
        const total = cost[i - 1][j] + jump + (j === k ? 0 : OCTAVE_SWITCH_PENALTY);
        if (total < best - 1e-9) {
          best = total;
          bestFrom = j;
        }
      }
      cost[i][k] = best;
      from[i][k] = bestFrom;
    }
  }

  let state = 0;
  for (let k = 1; k < OFFSETS.length; k += 1) {
    if (cost[count - 1][k] < cost[count - 1][state] - 1e-9) state = k;
  }
  const result = new Array<number>(count);
  for (let i = count - 1; i >= 0; i -= 1) {
    result[i] = values[i] + OFFSETS[state];
    state = from[i][state];
  }
  return result;
}
