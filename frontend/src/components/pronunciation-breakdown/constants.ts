import type { DiagnosticStatus, VowelZone } from "../StoryRecorder";

export const HEIGHT_LABEL: Record<VowelZone["height"], { zh: string; en: string }> = {
  high: { zh: "嘴巴小", en: "mouth close" }, mid: { zh: "嘴巴中", en: "mouth mid" }, low: { zh: "嘴巴大", en: "mouth open" },
};
export const BACKNESS_LABEL: Record<VowelZone["backness"], { zh: string; en: string }> = {
  front: { zh: "舌頭前", en: "tongue front" }, central: { zh: "舌頭中", en: "tongue centre" }, back: { zh: "舌頭後", en: "tongue back" },
};
export const HEIGHT_SHORT: Record<VowelZone["height"], string> = { high: "小", mid: "中", low: "大" };
export const BACKNESS_SHORT: Record<VowelZone["backness"], string> = { front: "前", central: "中", back: "後" };
export const NO_VOWEL_REASON: Record<string, { zh: string; en: string }> = {
  not_applicable: { zh: "這個字沒有單獨的母音", en: "This syllable has no single vowel to measure" },
  no_formants: { zh: "這個字太短，量不到", en: "Too short or too quiet to measure" },
  not_measured: { zh: "這次沒有量母音", en: "Vowels were not measured for this attempt" },
};
export const TONE_STATUS: Record<DiagnosticStatus, { mark: string; zh: string; en: string; tone: string }> = {
  CORRECT: { mark: "✓", zh: "聲調對了", en: "Tone correct", tone: "pass" },
  UNCERTAIN: { mark: "△", zh: "聽不太出來", en: "Not clear enough to judge", tone: "uncertain" },
  INCORRECT: { mark: "✗", zh: "聲調可能不一樣", en: "Likely tone mismatch", tone: "fail" },
  INVALID_AUDIO: { mark: "↻", zh: "請再錄一次", en: "Could not evaluate — please record again", tone: "retry" },
};
export const NEUTRAL_LABEL = { mark: "–", zh: "輕聲，不另外評分", en: "Neutral tone — not separately scored", tone: "not-measured" };
export const REASON_TEXT: Record<string, { zh: string; en: string }> = {
  neutral_tone_has_no_contour_target: { zh: "輕聲沒有固定的調型，所以不打分", en: "Neutral tone has no fixed pitch shape, so it is not scored" },
  segment_too_short_to_measure: { zh: "這個字太短，量不到調型", en: "This syllable was too short to measure" },
  insufficient_pitch_evidence: { zh: "這個字的聲音太少，沒辦法判斷", en: "Not enough voiced pitch to judge this syllable" },
  no_contour_measurement: { zh: "沒有量到調型", en: "No pitch measurement for this syllable" },
  contour_match_inconclusive: { zh: "調型有點接近，但不夠清楚", en: "The pitch movement was close but not clear" },
  contour_matches_expected_tone: { zh: "調型跟目標一樣", en: "The pitch moved the way this tone should" },
  contour_contradicts_expected_tone: { zh: "調型跟目標相反", en: "The pitch moved the opposite way from this tone" },
  recording_quality_unusable: { zh: "這次錄音沒辦法分析", en: "This recording could not be analysed" },
};
export const RULE_TEXT: Record<string, { zh: string; en: string }> = {
  T3_T3: { zh: "三聲變調：前面那個念二聲", en: "third-tone sandhi: the first one becomes a rising tone" },
  T3_CHAIN_AMBIGUOUS_GROUPING: { zh: "連續三聲，兩種說法都可以", en: "third-tone run — either reading is accepted" },
  YI_SANDHI: { zh: "一 的變調", en: "一 changes tone here" }, BU_SANDHI: { zh: "不 的變調", en: "不 changes tone here" },
  CONTEXTUAL_NEUTRAL_ALLOWED: { zh: "這裡念輕聲也可以", en: "neutral tone also accepted here" }, NEUTRAL_LEXICAL: { zh: "輕聲", en: "neutral tone" },
};
export const SUMMARY_BUCKETS = [
  { key: "correct", zh: "個對了", en: "correct" }, { key: "uncertain", zh: "個聽不太出來", en: "not clear" },
  { key: "incorrect", zh: "個要練", en: "to practise" }, { key: "invalid", zh: "個要再錄", en: "to re-record" },
] as const;
