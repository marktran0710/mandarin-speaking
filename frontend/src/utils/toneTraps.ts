import { numericToToneMarked } from "./pinyin";

// Tone-trap distractors for pinyin quiz questions: readings that differ from
// the correct one by exactly one syllable's tone (hē chá → hé chá / hē chà…).
// Much harder to eliminate than another word's completely different pinyin,
// and generated deterministically — no AI round-trip needed.

// Marked vowel → [base letter (v = ü), tone 1-4]. Built once from the same
// numeric→marked conversion pinyin.ts uses, so the two can't drift apart.
const MARKED_VOWELS = new Map<string, { base: string; tone: number }>();
for (const base of ["a", "e", "i", "o", "u", "v"]) {
  for (let tone = 1; tone <= 4; tone++) {
    const marked = numericToToneMarked(base + tone);
    MARKED_VOWELS.set(marked, { base, tone });
  }
}

const PLAIN_LETTERS = /^[a-zü]$/i;

/** Parses one tone-marked syllable into its numeric form ("chá" → "cha2",
 * neutral "ma" → "ma5") — null when it contains anything that isn't pinyin. */
function toNumericSyllable(syllable: string): string | null {
  let letters = "";
  let tone = 5;
  for (const char of syllable) {
    const marked = MARKED_VOWELS.get(char);
    if (marked) {
      letters += marked.base;
      tone = marked.tone;
      continue;
    }
    if (!PLAIN_LETTERS.test(char)) return null;
    letters += char === "ü" || char === "Ü" ? "v" : char;
  }
  return letters ? letters + tone : null;
}

/** Every reading of `pinyin` (tone-marked, space-separated syllables) that
 * differs in exactly one syllable's tone, using tones 1-4. Returns [] for
 * input that isn't parseable pinyin. */
export function toneTrapVariants(pinyin: string): string[] {
  const syllables = pinyin.trim().split(/\s+/).filter(Boolean);
  if (syllables.length === 0) return [];

  const numeric = syllables.map(toNumericSyllable);
  if (numeric.some((syl) => syl === null)) return [];

  const variants = new Set<string>();
  numeric.forEach((syl, index) => {
    const originalTone = Number(syl!.slice(-1));
    const base = syl!.slice(0, -1);
    for (let tone = 1; tone <= 4; tone++) {
      if (tone === originalTone) continue;
      const reToned = numericToToneMarked(base + tone);
      const variant = syllables
        .map((original, i) => (i === index ? reToned : original))
        .join(" ");
      if (variant !== pinyin) variants.add(variant);
    }
  });
  return [...variants];
}
