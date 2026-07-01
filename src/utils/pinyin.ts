import { pinyin, customPinyin } from "pinyin-pro";

// Taiwan Mandarin (國語/臺灣華語) overrides.
// Two main differences from Mainland Standard (普通話):
//   1. Some words have entirely different base readings (e.g. 垃圾 lè sè vs lā jī).
//   2. Taiwan preserves full tones for syllables that became neutral tones (輕聲)
//      in Mainland Mandarin (e.g. 喜歡 xǐ huān vs xǐ huan).
customPinyin({
  // ── Different base reading ────────────────────────────────────────────────
  "垃圾": "lè sè",

  // ── Directional complements keep full tone in Taiwan ─────────────────────
  "出來": "chū lái",
  "進來": "jìn lái",
  "回來": "huí lái",
  "起來": "qǐ lái",
  "下來": "xià lái",
  "上來": "shàng lái",
  "過來": "guò lái",
  "出去": "chū qù",
  "進去": "jìn qù",
  "回去": "huí qù",
  "起去": "qǐ qù",

  // ── Common compound words: neutral → full tone ────────────────────────────
  "告訴": "gào sù",
  "知道": "zhī dào",
  "喜歡": "xǐ huān",
  "朋友": "péng yǒu",
  "東西": "dōng xī",
  "地方": "dì fāng",
  "意思": "yì sī",
  "客氣": "kè qì",
  "窗戶": "chuāng hù",
  "時候": "shí hòu",
  "先生": "xiān shēng",
  "學生": "xué shēng",
  "事情": "shì qíng",
  "麻煩": "má fán",
  "厲害": "lì hài",
  "豆腐": "dòu fǔ",
  "謝謝": "xiè xiè",
  "頭髮": "tóu fà",
  "石頭": "shí tóu",
  "木頭": "mù tóu",
  "饅頭": "mán tóu",
  "念頭": "niàn tóu",
  "拳頭": "quán tóu",
  "枕頭": "zhěn tóu",
  "沒有": "méi yǒu",
  "規矩": "guī jǔ",
  "力氣": "lì qì",
  "運氣": "yùn qì",
  "消息": "xiāo xī",
  "熱鬧": "rè nào",
  "笑話": "xiào huà",
  "故事": "gù shì",
  "將來": "jiāng lái",
  "眼睛": "yǎn jīng",
  "耳朵": "ěr duǒ",
  "腦袋": "nǎo dài",
  "嘴巴": "zuǐ bā",
  "肚子": "dù zǐ",
  "鼻子": "bí zǐ",
  "脖子": "bó zǐ",
  "身子": "shēn zǐ",
  "帽子": "mào zǐ",
  "椅子": "yǐ zǐ",
  "桌子": "zhuō zǐ",
  "箱子": "xiāng zǐ",
  "盒子": "hé zǐ",
  "鞋子": "xié zǐ",
  "杯子": "bēi zǐ",
  "瓶子": "píng zǐ",
  "本子": "běn zǐ",
  "句子": "jù zǐ",
  "日子": "rì zǐ",
  "樣子": "yàng zǐ",
  "法子": "fǎ zǐ",
  "面子": "miàn zǐ",
  "孩子": "hái zǐ",
  "兔子": "tù zǐ",
  "獅子": "shī zǐ",
  "猴子": "hóu zǐ",
  "分子": "fèn zǐ",
});

// Tone-mark tables indexed 0–4 (tone 1–4 plus neutral/5 = no mark)
const TONE_MARKS: Record<string, string[]> = {
  a: ["ā", "á", "ǎ", "à", "a"],
  e: ["ē", "é", "ě", "è", "e"],
  i: ["ī", "í", "ǐ", "ì", "i"],
  o: ["ō", "ó", "ǒ", "ò", "o"],
  u: ["ū", "ú", "ǔ", "ù", "u"],
  v: ["ǖ", "ǘ", "ǚ", "ǜ", "ü"], // ü written as v or u:
};

function applySyllableTone(syl: string): string {
  // Match optional leading consonants, vowel run, optional coda, then digit
  const m = syl.match(/^([^aeiouüv]*)([aeiouüv]+)([^aeiouüv\d]*)([1-5])$/i);
  if (!m) return syl;
  const [, onset, nucleus, coda, toneDigit] = m;
  const tone = parseInt(toneDigit) - 1; // 0-indexed
  const n = nucleus.toLowerCase();

  let marked = nucleus;
  // Rule 1: a or e gets the mark
  if (n.includes("a")) {
    marked = nucleus.replace(/a/i, TONE_MARKS.a[tone]);
  } else if (n.includes("e")) {
    marked = nucleus.replace(/e/i, TONE_MARKS.e[tone]);
  // Rule 2: "ou" → mark on o
  } else if (n === "ou") {
    marked = TONE_MARKS.o[tone] + "u";
  } else {
    // Rule 3: last vowel in the nucleus gets the mark
    const vowelOrder = ["v", "u", "i", "o"];
    for (const v of vowelOrder) {
      const last = n.lastIndexOf(v);
      if (last !== -1) {
        marked =
          nucleus.slice(0, last) +
          TONE_MARKS[v][tone] +
          nucleus.slice(last + 1);
        break;
      }
    }
  }
  return onset + marked + coda;
}

/**
 * Convert numeric-tone pinyin (e.g. "wo3 men5", "ni3 hao3") to
 * tone-marked pinyin ("wǒ men", "nǐ hǎo"). Syllables without a trailing
 * digit are left unchanged, so mixed input like "nǐ hao3" also works.
 */
export function numericToToneMarked(input: string): string {
  // Split on word boundaries while preserving delimiters (spaces, commas, etc.)
  return input.replace(/[a-züv]+[1-5]/gi, applySyllableTone);
}

const cache = new Map<string, string>();

/**
 * Convert a Chinese word/phrase to tone-marked pinyin using Taiwan Mandarin
 * (國語) pronunciation. Results are memoized. Non-Chinese input is returned
 * unchanged so the helper is safe to call on any vocabulary chip.
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
    result = "";
  }

  cache.set(word, result);
  return result;
}
