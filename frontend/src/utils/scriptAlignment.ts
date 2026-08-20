/**
 * Filters a string down to the characters we align on — letters and digits
 * only. Punctuation is ignored because ASR output is inconsistent about it.
 */
function alignableChars(text: string | undefined): string[] {
  return Array.from((text ?? "").normalize("NFKC")).filter((char) => /[\p{L}\p{N}]/u.test(char));
}

/**
 * Mandarin has a small number of orthographic variants that are pronounced
 * identically in a learner's recording. They should not break transcript
 * alignment, but the original characters must remain available for the UI.
 * Keep this list deliberately narrow: characters with the same pronunciation
 * but different meaning (for example 她/他) are still meaningful mismatches.
 */
const SCRIPT_COMPARE_EQUIVALENTS: Record<string, string> = {
  妳: "你",
};

function scriptComparisonKey(char: string): string {
  return SCRIPT_COMPARE_EQUIVALENTS[char] ?? char;
}

interface CharAlignment {
  expected: string[];
  spoken: string[];
  /** True when expected[i] was matched to some character in spoken. */
  matched: boolean[];
  /** The spoken-array index expected[i] matched to, or null when unmatched. */
  spokenIndex: (number | null)[];
}

/**
 * Longest-common-subsequence alignment between two character streams. Keeps
 * repeated characters in their most plausible order, so every unmatched
 * expected character is either missing or was replaced by what the learner
 * said at that point.
 */
function alignChars(expectedText: string | undefined, spokenText: string | undefined): CharAlignment {
  const expected = alignableChars(expectedText);
  const spoken = alignableChars(spokenText);
  const expectedKeys = expected.map(scriptComparisonKey);
  const spokenKeys = spoken.map(scriptComparisonKey);
  const matched = new Array<boolean>(expected.length).fill(false);
  const spokenIndex = new Array<number | null>(expected.length).fill(null);

  // Do not mark anything as matched until we have a real transcript.
  if (expected.length === 0 || spoken.length === 0) {
    return { expected, spoken, matched, spokenIndex };
  }

  const width = spoken.length + 1;
  const table = new Uint16Array((expected.length + 1) * width);
  const at = (row: number, column: number) => row * width + column;
  for (let row = 1; row <= expected.length; row += 1) {
    for (let column = 1; column <= spoken.length; column += 1) {
      table[at(row, column)] = expectedKeys[row - 1] === spokenKeys[column - 1]
        ? table[at(row - 1, column - 1)] + 1
        : Math.max(table[at(row - 1, column)], table[at(row, column - 1)]);
    }
  }

  let row = expected.length;
  let column = spoken.length;
  while (row > 0 && column > 0) {
    if (expectedKeys[row - 1] === spokenKeys[column - 1]) {
      matched[row - 1] = true;
      spokenIndex[row - 1] = column - 1;
      row -= 1;
      column -= 1;
    } else if (table[at(row - 1, column)] >= table[at(row, column - 1)]) {
      row -= 1;
    } else {
      column -= 1;
    }
  }

  return { expected, spoken, matched, spokenIndex };
}

/**
 * Returns every part of the model script that was not aligned with the
 * learner's transcript. We compare the complete utterance, not just a small
 * vocabulary list, so a learner can see every missing or substituted part of
 * the sentence.
 */
export function scriptMismatchTokens(script: string | undefined, transcript: string | undefined): string[] {
  const { expected, spoken, matched } = alignChars(script, transcript);

  // Do not mark an entire script as wrong until we have a real transcript.
  if (expected.length === 0 || spoken.length === 0) return [];

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

/**
 * Fraction of `script`'s alignable characters that were actually found (via
 * LCS alignment, so out-of-order ASR noise doesn't count against it) in
 * `transcript`. Used where a single ASR slip inside a longer phrase
 * shouldn't fail the whole phrase the way an exact-substring check would —
 * ASR errors are noisier than genuine mispronunciation, so this is
 * deliberately more forgiving than a per-word tone-pass ratio.
 *
 * Returns 1 for an empty script (nothing to mismatch) and 0 when there is no
 * transcript yet to compare against.
 */
export function scriptMatchRatio(script: string | undefined, transcript: string | undefined): number {
  const expectedChars = alignableChars(script);
  if (expectedChars.length === 0) return 1;
  if (alignableChars(transcript).length === 0) return 0;
  const { matched } = alignChars(script, transcript);
  const matchedCount = matched.filter(Boolean).length;
  return matchedCount / expectedChars.length;
}

/** Punctuation marks that separate one meaning-chunk of a script from the
 * next. Splitting on these — rather than running clause-detection NLP — lets
 * a teacher control chunk boundaries just by how they punctuate the script
 * they already write. */
const CHUNK_BOUNDARY = /[，,、。.！!？?；;：:]+/u;

/** A teacher can set exact phrase boundaries with punctuation. For a long
 * unpunctuated Mandarin model sentence, however, returning the entire text as
 * one "chunk" defeats focused repair. This conservative fallback keeps short
 * phrases intact and slices only longer runs into speakable five-character
 * parts. Punctuation still always wins when it is available. */
const AUTO_CHUNK_MAX_CHARS = 5;

function splitLongUnpunctuatedChunk(text: string): string[] {
  const chars = Array.from(text);
  if (chars.length <= AUTO_CHUNK_MAX_CHARS) return [text];
  const chunks: string[] = [];
  for (let start = 0; start < chars.length; start += AUTO_CHUNK_MAX_CHARS) {
    chunks.push(chars.slice(start, start + AUTO_CHUNK_MAX_CHARS).join(""));
  }
  return chunks;
}

/**
 * Splits a teacher's script into meaning-chunks along its own punctuation.
 * Short scripts without an internal boundary remain intact; longer ones use
 * a conservative fallback so repair never turns into re-recording a whole
 * sentence.
 */
export function splitScriptIntoChunks(script: string | undefined): string[] {
  const trimmed = (script ?? "").trim();
  if (!trimmed) return [];
  const pieces = trimmed
    .split(CHUNK_BOUNDARY)
    .map((piece) => piece.trim())
    .filter(Boolean);
  if (pieces.length > 1) return pieces;
  return pieces.length === 1 ? splitLongUnpunctuatedChunk(pieces[0]) : [trimmed];
}

/**
 * Teacher-authored phrase boundaries only. Unlike `splitScriptIntoChunks`,
 * this never invents five-character chunks for an unpunctuated sentence. The
 * pronunciation breakdown uses this version so a teacher's phrase remains a
 * phrase instead of becoming a row of arbitrary mini-sentences.
 */
export function splitTeacherScriptIntoPhrases(script: string | undefined): string[] {
  const trimmed = (script ?? "").trim();
  if (!trimmed) return [];
  return trimmed
    .split(CHUNK_BOUNDARY)
    .map((piece) => piece.trim())
    .filter(Boolean);
}

/** Minimal shape scoreScriptChunks needs from a word_prosody entry — kept
 * local (rather than importing StoryRecorder's WordProsody type) to avoid a
 * dependency cycle; any WordProsody[] satisfies this structurally. */
export interface ProsodyToken {
  token: string;
  passed?: boolean | null;
}

export interface ScriptChunkScore<T extends ProsodyToken = ProsodyToken> {
  text: string;
  /** True once every alignable character in this chunk was matched in the
   * transcript AND every word_prosody token attributed to it passed. A chunk
   * with no attributed tokens at all (nothing recognizable was said for it
   * yet) is never marked passed. */
  passed: boolean;
  /** Characters from this chunk's script text the learner never said. */
  mismatch: string;
  /** word_prosody entries attributed to this chunk, in transcript order. */
  tokens: T[];
}

/**
 * Scores each script chunk against the learner's transcript + word_prosody.
 * word_prosody tokens are produced from the transcript in order and, once
 * concatenated, reconstruct the same filtered character stream the alignment
 * runs on — so each token can be attributed to a chunk by asking which
 * script chunk its *matched* transcript characters fall inside. A token with
 * no matched characters (entirely extraneous speech) inherits the
 * most-recently-seen chunk, since it was most likely said in that position.
 */
export function scoreScriptChunks<T extends ProsodyToken>(
  script: string | undefined,
  transcript: string | undefined,
  wordProsody: T[] | undefined,
  explicitChunks?: string[],
): ScriptChunkScore<T>[] {
  const chunks = explicitChunks?.length ? explicitChunks : splitScriptIntoChunks(script);
  if (chunks.length === 0) return [];

  const { expected, matched, spokenIndex } = alignChars(script, transcript);

  // Map each expected (script) char index to its chunk index, by walking the
  // chunks' own alignable-character counts over the same filtered stream.
  const chunkOfExpectedIndex: number[] = [];
  let expectedCursor = 0;
  chunks.forEach((chunk, chunkIndex) => {
    const length = alignableChars(chunk).length;
    for (let i = 0; i < length; i += 1) {
      chunkOfExpectedIndex[expectedCursor] = chunkIndex;
      expectedCursor += 1;
    }
  });

  // Map each matched spoken-char index back to its chunk, so tokens (which
  // are spoken-side) can look their characters up directly.
  const chunkOfSpokenIndex = new Map<number, number>();
  expected.forEach((_char, index) => {
    if (matched[index] && spokenIndex[index] !== null) {
      chunkOfSpokenIndex.set(spokenIndex[index]!, chunkOfExpectedIndex[index]);
    }
  });

  const buckets: T[][] = chunks.map(() => []);
  let spokenCursor = 0;
  let lastKnownChunk = 0;
  (wordProsody ?? []).forEach((item) => {
    const tokenChars = alignableChars(item.token);
    let chunkForToken: number | null = null;
    for (let i = 0; i < tokenChars.length; i += 1) {
      const chunk = chunkOfSpokenIndex.get(spokenCursor + i);
      if (chunk !== undefined) {
        chunkForToken = chunk;
        break;
      }
    }
    spokenCursor += tokenChars.length;
    if (chunkForToken === null) chunkForToken = lastKnownChunk;
    lastKnownChunk = chunkForToken;
    buckets[chunkForToken].push(item);
  });

  return chunks.map((text, chunkIndex) => {
    const tokens = buckets[chunkIndex];
    let mismatch = "";
    let allCharsMatched = true;
    expected.forEach((char, index) => {
      if (chunkOfExpectedIndex[index] !== chunkIndex) return;
      if (matched[index]) return;
      allCharsMatched = false;
      mismatch += char;
    });
    const allTokensPassed = tokens.length > 0 && tokens.every((item) => item.passed !== false);
    return {
      text,
      passed: allCharsMatched && allTokensPassed,
      mismatch,
      tokens,
    };
  });
}
