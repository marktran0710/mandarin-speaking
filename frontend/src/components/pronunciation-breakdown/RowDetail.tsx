import { ASSISTIVE_MESSAGE, type AssistiveFeedbackSyllable } from "../../utils/assistiveFeedback";
import { BiLabel } from "../BiLabel";
import StudentIcon from "../StudentIcon";
import MiniContourChart from "../pitch/MiniContourChart";
import type { WordProsody, WordProsodySyllable, VowelZone } from "../story-recorder/StoryRecorder";
import { BACKNESS_SHORT, HEIGHT_SHORT, NO_VOWEL_REASON, REASON_TEXT, RULE_TEXT } from "./constants";
import { isNeutral, statusLabel } from "./model";

const toneIcon = (tone: string) => tone === "pass" ? "check-circle" as const : tone === "fail" ? "x-circle" as const : tone === "retry" ? "retry" as const : "warning" as const;

function zoneText(zone: VowelZone, key: "zh" | "en"): string {
  const height = { high: { zh: "嘴巴小", en: "mouth close" }, mid: { zh: "嘴巴中", en: "mouth mid" }, low: { zh: "嘴巴大", en: "mouth open" } };
  const backness = { front: { zh: "舌頭前", en: "tongue front" }, central: { zh: "舌頭中", en: "tongue centre" }, back: { zh: "舌頭後", en: "tongue back" } };
  return `${height[zone.height][key]}・${backness[zone.backness][key]}`;
}

export function VowelChip({ syllable }: { syllable: WordProsodySyllable }) {
  const zone = syllable.measured_zone;
  if (!zone) {
    const reason = NO_VOWEL_REASON[syllable.vowel_status ?? "not_measured"] ?? NO_VOWEL_REASON.not_measured;
    return <span className="pb-vowel--none" title={`${reason.zh} — ${reason.en}`}>—</span>;
  }
  return <span className="pb-vowel-chip" lang="zh-Hant">嘴型 {HEIGHT_SHORT[zone.height]}・{BACKNESS_SHORT[zone.backness]}
    {syllable.vowel_status === "nucleus_only" && <abbr className="pb-vowel-glide" title="這個韻母會滑動，只量中間 — this final glides, so only its middle was measured">~</abbr>}
  </span>;
}

export function RowDetail({ syllable, word, referenceAccepted = false, debug, assistiveRecord = null }: {
  syllable: WordProsodySyllable; word: WordProsody; referenceAccepted?: boolean; debug: boolean; assistiveRecord?: AssistiveFeedbackSyllable | null;
}) {
  const label = statusLabel(syllable, referenceAccepted);
  const reason = !referenceAccepted && !isNeutral(syllable) && syllable.diagnostic_reason ? REASON_TEXT[syllable.diagnostic_reason] : undefined;
  const rule = syllable.context_rule ? RULE_TEXT[syllable.context_rule] : undefined;
  const zone = syllable.measured_zone;
  return <div className="pb-detail">
    {(word.pitch_contour?.length || word.user_curve?.length) && <div className="pb-detail-contour" aria-label={`${word.token} tone visualization`}><MiniContourChart actual={word.pitch_contour} reference={word.reference_contour} userCurve={word.user_curve} targetCurve={word.target_curve} /></div>}
    <p className={`pb-detail-status is-${label.tone}`}><span aria-hidden="true"><StudentIcon name={toneIcon(label.tone)} size={16} /></span>{" "}<BiLabel zh={label.zh} en={label.en} /></p>
    {reason && <p className="pb-detail-line"><BiLabel zh={reason.zh} en={reason.en} /></p>}
    {rule && <p className="pb-detail-line pb-detail-rule"><BiLabel zh={rule.zh} en={rule.en} /></p>}
    {assistiveRecord && assistiveRecord.assistive_state !== "ACCEPT" && <p className="pb-detail-line pb-detail-assistive" data-assistive-state={assistiveRecord.assistive_state}>{ASSISTIVE_MESSAGE[assistiveRecord.assistive_state]}</p>}
    {zone && <div className="pb-detail-vowel">
      {syllable.expected_vowel && <p className="pb-detail-line"><span className="pb-detail-label" lang="zh-Hant">要說</span>{" "}<em>{syllable.expected_vowel === "v" ? "ü" : syllable.expected_vowel}</em>{" "}{syllable.expected_zone && <span lang="zh-Hant">{zoneText(syllable.expected_zone, "zh")}</span>}</p>}
      <p className="pb-detail-line"><span className="pb-detail-label" lang="zh-Hant">你說</span>{" "}<span lang="zh-Hant">{zoneText(zone, "zh")}</span><small lang="en">{" "}— {zoneText(zone, "en")}{(syllable.f1 ?? 0) > 0 && <> · F1 {Math.round(syllable.f1 ?? 0)} · F2 {Math.round(syllable.f2 ?? 0)} Hz</>}</small></p>
    </div>}
    {debug && <p className="pb-detail-debug">Contour match: {syllable.contour_match_score ?? "—"}/100 · provenance: {syllable.score_provenance ?? "unknown"} · legacy gate: {syllable.legacy?.passed === true ? "PASS" : syllable.legacy?.passed === false ? "FAIL" : "n/a"} ({syllable.legacy?.score ?? syllable.score} vs {syllable.legacy?.threshold ?? 58})</p>}
  </div>;
}
