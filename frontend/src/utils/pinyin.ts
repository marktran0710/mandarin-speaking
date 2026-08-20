const BACKEND_URL =
  import.meta.env.VITE_BACKEND_URL ||
  (import.meta.env.DEV && typeof window !== "undefined" ? window.location.origin : "");

const canonicalCache = new Map<string, string>();

/**
 * Warm the frontend cache from the backend's single Taiwan Mandarin pinyin
 * source. The request is batched so a story does not make one network call
 * per vocabulary item.
 *
 * There is deliberately no local dictionary fallback: every Chinese pinyin
 * value used by the UI must come from this backend response.
 */
export async function primePinyin(texts: string[]): Promise<void> {
  const uniqueTexts = [...new Set(
    texts.map((text) => text.trim()).filter(Boolean),
  )];
  const missing = uniqueTexts.filter((text) => !canonicalCache.has(text));
  if (missing.length === 0) return;

  // Keep requests below the API validation limit even for a large teacher
  // story collection.
  for (let offset = 0; offset < missing.length; offset += 400) {
    const response = await fetch(`${BACKEND_URL}/api/pinyin`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ texts: missing.slice(offset, offset + 400) }),
    });
    if (!response.ok) {
      throw new Error(`Canonical pinyin request failed (${response.status}).`);
    }

    const data = (await response.json()) as {
      items?: Array<{ text?: string; pinyin?: string }>;
    };
    for (const item of data.items ?? []) {
      const text = item.text?.trim();
      if (text && typeof item.pinyin === "string") {
        canonicalCache.set(text, item.pinyin);
      }
    }
  }
}

/**
 * Synchronous read used by existing render/quiz code after App boot has
 * primed the cache for every published story.
 */
export function toPinyin(text: string): string {
  const word = text.trim();
  if (!word) return "";

  const canonical = canonicalCache.get(word);
  return canonical ?? "";
}

// Tone-mark tables indexed 0-4 (tone 1-4 plus neutral/5 = no mark).
const TONE_MARKS: Record<string, string[]> = {
  a: ["ā", "á", "ǎ", "à", "a"],
  e: ["ē", "é", "ě", "è", "e"],
  i: ["ī", "í", "ǐ", "ì", "i"],
  o: ["ō", "ó", "ǒ", "ò", "o"],
  u: ["ū", "ú", "ǔ", "ù", "u"],
  v: ["ǖ", "ǘ", "ǚ", "ǜ", "ü"],
};

function applySyllableTone(syllable: string): string {
  const match = syllable.match(/^([^aeiouvü]*)([aeiouvü]+)([^aeiouvü\d]*)([1-5])$/i);
  if (!match) return syllable;
  const [, onset, nucleus, coda, toneDigit] = match;
  const tone = Number(toneDigit) - 1;
  const lower = nucleus.toLowerCase();

  let marked = nucleus;
  if (lower.includes("a")) {
    marked = nucleus.replace(/a/i, TONE_MARKS.a[tone]);
  } else if (lower.includes("e")) {
    marked = nucleus.replace(/e/i, TONE_MARKS.e[tone]);
  } else if (lower === "ou") {
    marked = TONE_MARKS.o[tone] + "u";
  } else {
    for (const vowel of ["v", "ü", "u", "i", "o"]) {
      const index = lower.lastIndexOf(vowel);
      if (index < 0) continue;
      const key = vowel === "ü" ? "v" : vowel;
      marked = nucleus.slice(0, index) + TONE_MARKS[key][tone] + nucleus.slice(index + 1);
      break;
    }
  }
  return onset + marked + coda;
}

/** Convert numeric pinyin such as "wo3 men5" to tone-marked pinyin. */
export function numericToToneMarked(input: string): string {
  return input.replace(/[a-züv]+[1-5]/gi, applySyllableTone);
}

/** Return pinyin split per character when the backend reading aligns. */
export function toPinyinSyllables(text: string): string[] {
  const word = text.trim();
  const syllables = toPinyin(word).split(/\s+/).filter(Boolean);
  return syllables.length === [...word].length ? syllables : [];
}
