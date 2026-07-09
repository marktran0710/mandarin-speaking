export type ScoreTier = "excellent" | "good" | "ok" | "low";

const TIER_LABELS: Record<ScoreTier, { zh: string; pinyin: string; en: string }> = {
  excellent: { zh: "非常好", pinyin: "Fēicháng hǎo", en: "Excellent" },
  good: { zh: "不錯", pinyin: "Búcuò", en: "Good" },
  ok: { zh: "還可以", pinyin: "Hái kěyǐ", en: "Needs practice" },
  low: { zh: "再試試", pinyin: "Zài shìshi", en: "Keep trying" },
};

/** Buckets a 0-100 Praat score into one of four tiers, shared by every
 * score display in the app (word-practice drill, scene-vocab practice,
 * Tone Practice page, post-recording summary) so the wording and
 * thresholds stay consistent instead of each screen keeping its own copy. */
export function scoreTier(score: number): ScoreTier {
  if (score >= 85) return "excellent";
  if (score >= 68) return "good";
  if (score >= 48) return "ok";
  return "low";
}

/** The bilingual label for a tier, e.g. `{ zh: "不錯", pinyin: "Búcuò", en: "Good" }` —
 * pass straight into `<BiLabel zh={...} pinyin={...} en={...} />`. */
export function scoreTierLabel(tier: ScoreTier): { zh: string; pinyin: string; en: string } {
  return TIER_LABELS[tier];
}
