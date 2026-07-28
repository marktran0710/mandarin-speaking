/**
 * Returns every part of the model script that was not aligned with the
 * learner's transcript. We compare the complete utterance, not just a small
 * vocabulary list, so a learner can see every missing or substituted part of
 * the sentence. Punctuation is ignored because ASR output is inconsistent
 * about it.
 */
export function scriptMismatchTokens(script: string | undefined, transcript: string | undefined): string[] {
  const expected = Array.from((script ?? "").normalize("NFKC")).filter((char) => /[\p{L}\p{N}]/u.test(char));
  const spoken = Array.from((transcript ?? "").normalize("NFKC")).filter((char) => /[\p{L}\p{N}]/u.test(char));

  // Do not mark an entire script as wrong until we have a real transcript.
  if (expected.length === 0 || spoken.length === 0) return [];

  // Longest-common-subsequence alignment keeps repeated characters in their
  // most plausible order. Every unmatched script character is either missing
  // or was replaced by what the learner said at that point.
  const width = spoken.length + 1;
  const table = new Uint16Array((expected.length + 1) * width);
  const at = (row: number, column: number) => row * width + column;
  for (let row = 1; row <= expected.length; row += 1) {
    for (let column = 1; column <= spoken.length; column += 1) {
      table[at(row, column)] = expected[row - 1] === spoken[column - 1]
        ? table[at(row - 1, column - 1)] + 1
        : Math.max(table[at(row - 1, column)], table[at(row, column - 1)]);
    }
  }

  const matched = new Array<boolean>(expected.length).fill(false);
  let row = expected.length;
  let column = spoken.length;
  while (row > 0 && column > 0) {
    if (expected[row - 1] === spoken[column - 1]) {
      matched[row - 1] = true;
      row -= 1;
      column -= 1;
    } else if (table[at(row - 1, column)] >= table[at(row, column - 1)]) {
      row -= 1;
    } else {
      column -= 1;
    }
  }

  const mismatches: string[] = [];
  let current = "";
  expected.forEach((char, index) => {
    if (!matched[index]) {
      current += char;
      return;
    }
    if (current) mismatches.push(current);
    current = "";
  });
  if (current) mismatches.push(current);
  return mismatches;
}
