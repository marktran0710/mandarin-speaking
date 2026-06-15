import { pinyin } from "pinyin-pro";

const cache = new Map<string, string>();

/**
 * Convert a Chinese word/phrase to tone-marked pinyin (e.g. 你好 → "nǐ hǎo").
 * Results are memoized. Non-Chinese input is returned unchanged so the helper
 * is safe to call on any vocabulary chip.
 */
export function toPinyin(text: string): string {
  const word = text.trim();
  if (!word) return "";

  const cached = cache.get(word);
  if (cached !== undefined) return cached;

  let result = word;
  if (/[一-鿿]/.test(word)) {
    try {
      result = pinyin(word, { toneType: "symbol", type: "string" });
    } catch {
      result = "";
    }
  } else {
    // No Han characters — nothing to annotate.
    result = "";
  }

  cache.set(word, result);
  return result;
}
