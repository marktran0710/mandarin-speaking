import { useEffect, useMemo, useState } from "react";
import { ASSISTIVE_MESSAGE, matchAssistiveRecord } from "../../utils/assistiveFeedback";
import { primePinyin } from "../../utils/pinyin";
import { scriptAlignmentText } from "../../utils/scriptAlignment";
import { toneArrow } from "../../utils/storyRecorderFeedback";
import { BiLabel } from "../BiLabel";
import { SUMMARY_BUCKETS, TONE_STATUS } from "./constants";
import { breakdownGroups, breakdownPhraseGroups, countByBucket, displayWordsForScript, referenceEvidenceAccepted, statusLabel } from "./model";
import { RowDetail, VowelChip } from "./RowDetail";
import type { PronunciationBreakdownProps } from "./types";

const actionable = (tone: string) => tone === "fail" || tone === "uncertain" || tone === "retry";

export default function BreakdownView({ words, targetText, transcription, teacherPhrases, debug = false, compact = false, assistiveFeedback = null, masteryCounts }: PronunciationBreakdownProps) {
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [showAllRows, setShowAllRows] = useState(false);
  const [pinyinRevision, setPinyinRevision] = useState(0);
  const displayWords = useMemo(() => displayWordsForScript(words, targetText, transcription), [words, targetText, transcription, pinyinRevision]);
  const tokens = useMemo(() => [...new Set([...displayWords.map((word) => word.token.trim()).filter((token) => /[\u3400-\u9fff]/u.test(token)), scriptAlignmentText(targetText), scriptAlignmentText(transcription)].filter(Boolean))], [displayWords, targetText, transcription]);
  useEffect(() => { let active = true; if (tokens.length) void primePinyin(tokens).then(() => { if (active) setPinyinRevision((v) => v + 1); }).catch(() => {}); return () => { active = false; }; }, [tokens.join("\u0000")]);
  const groups = useMemo(() => breakdownGroups(displayWords), [displayWords, pinyinRevision]);
  if (!groups.length) return null;
  const phrases = breakdownPhraseGroups(groups, targetText, transcription, teacherPhrases);
  const counts = countByBucket(groups);
  const summary = SUMMARY_BUCKETS.filter((bucket) => counts[bucket.key] > 0);
  const total = groups.reduce((sum, group) => sum + group.rows.length, 0);
  const hasActionable = groups.some((group) => group.rows.some(({ syllable, word }) => actionable(statusLabel(syllable, referenceEvidenceAccepted(word)).tone)));
  const hidePassed = compact && hasActionable && !showAllRows;
  const hidden = hidePassed ? groups.reduce((sum, group) => sum + group.rows.filter(({ syllable, word }) => {
    const tone = statusLabel(syllable, referenceEvidenceAccepted(word)).tone;
    return tone === "pass" || tone === "not-measured";
  }).length, 0) : 0;
  let flatIndex = -1;

  return <section className="pronunciation-breakdown" aria-label="Pronunciation breakdown">
    <div className="pb-head"><div className="pb-head-top"><div className="pb-head-copy">
      <p className="block-label pb-heading"><BiLabel zh="發音分析" pinyin="Fāyīn fēnxī" en="Pronunciation breakdown" /></p>
      <p className="pb-head-meta"><strong>{total}</strong><span>音節顯示 / syllables shown</span>{counts.neutral > 0 && <><span className="pb-head-meta-divider" aria-hidden="true">·</span><strong>{counts.neutral}</strong><span>輕聲不計 / neutral excluded</span></>}{counts.not_scored > 0 && <><span className="pb-head-meta-divider" aria-hidden="true">·</span><strong>{counts.not_scored}</strong><span>未計入 / not counted</span></>}</p>
    </div>{masteryCounts && masteryCounts.total > 0 && <div className="pb-head-score" role="status" aria-atomic="true" aria-label={masteryCounts.passed + " of " + masteryCounts.total + " syllables counted for progress"}><span className="pb-head-score-label">本次進度 / Progress</span><strong>{masteryCounts.passed}<span>/{masteryCounts.total}</span></strong><small>計入過關 / counted</small></div>}</div>
    {summary.length > 0 && <div className="pb-summary-row" role="status" aria-atomic="true" aria-label={total + " syllable detail rows: " + summary.map((bucket) => counts[bucket.key] + " " + bucket.en).join(", ")}><span className="pb-summary-label">細項 / Detail</span><div className="pb-summary">{summary.map((bucket) => <span key={bucket.key} className={"pb-summary-item is-" + bucket.key}><span className="pb-summary-dot" aria-hidden="true" /><strong>{counts[bucket.key]}</strong><span lang="zh-Hant">{bucket.zh}</span><small lang="en">{bucket.en}</small></span>)}</div></div>}
    </div>
    <ul className="pb-legend">{(["CORRECT", "UNCERTAIN", "INCORRECT", "INVALID_AUDIO"] as const).map((status) => <li key={status} className={"pb-legend-item is-" + TONE_STATUS[status].tone}><span className="pb-mark" aria-hidden="true">{TONE_STATUS[status].mark}</span><BiLabel zh={TONE_STATUS[status].zh} en={TONE_STATUS[status].en} /></li>)}</ul>
    {compact && hasActionable && hidden > 0 && <button type="button" className="pb-compact-toggle" aria-expanded={showAllRows} onClick={() => setShowAllRows((open) => !open)}>{showAllRows ? <BiLabel zh="只看需要練習的部分" en="Show only parts to practise" /> : <BiLabel zh={"顯示全部發音 (" + hidden + " 個已通過)"} en={"Show all pronunciation rows (" + hidden + " passed)"} />}</button>}
    <div className="pb-groups">{phrases.map((phrase) => {
      const hasFail = phrase.words.some((group) => group.rows.some(({ syllable, word }) => statusLabel(syllable, referenceEvidenceAccepted(word)).tone === "fail"));
      const hasVisibleAction = phrase.words.some((group) => group.rows.some(({ syllable, word }) => actionable(statusLabel(syllable, referenceEvidenceAccepted(word)).tone)));
      const phraseClass = "pb-phrase-group" + (phrase.text ? "" : " is-unstructured") + (phrase.uncertain ? " is-uncertain" : phrase.passed === true ? " is-passed" : phrase.passed === false ? " is-needs-practice" : "") + (hasFail ? " has-fail" : "");
      return <section className={phraseClass} key={phrase.key}>
        {phrase.text && <div className="pb-phrase-header"><span className="pb-phrase-label" lang="zh-Hant">{phrase.text}</span><span className="pb-phrase-note">{phrase.uncertain ? "not enough evidence" : phrase.passed === true ? "phrase ready" : phrase.passed === false ? "needs practice" : "word detail"}</span></div>}
        <div className="pb-phrase-words">{phrase.words.map((group) => {
          if (hidePassed && !group.rows.some(({ syllable, word }) => actionable(statusLabel(syllable, referenceEvidenceAccepted(word)).tone))) return null;
          const record = group.rows[0]?.word;
          const showScores = typeof record?.shape_score === "number" && typeof record?.direction_score === "number";
          const display = typeof record?.display_score === "number" ? Math.round(record.display_score) : null;
          return <div className="pb-group" key={group.key}><p className="pb-group-header"><span className="pb-group-token" lang="zh-Hant">{group.token}</span>{group.pinyin && <span className="pb-group-pinyin">{group.pinyin}</span>}{showScores && <span className="pb-group-scores" title="shape · direction · overall"><small>shape {Math.round(record.shape_score!)}{" · "}dir {Math.round(record.direction_score!)}{display !== null && <>{" · "}overall {display}</>}</small></span>}</p>
            {record?.reason === "weak_shape" && <p className="pb-group-note"><BiLabel zh="音高的整體形狀還不夠像目標聲調。慢慢多練幾次。" en="The overall pitch shape is not quite matching the target tone yet. Practise it slowly a few more times." /></p>}
            <ul className="pb-rows">{group.rows.map(({ key, char, pinyin, syllable, word }) => {
              const index = ++flatIndex;
              const assistiveRecord = matchAssistiveRecord(assistiveFeedback, index, char);
              const accepted = referenceEvidenceAccepted(word);
              const label = statusLabel(syllable, accepted);
              if (hidePassed && !actionable(label.tone)) return null;
              const open = openKey === key;
              return <li key={key} className="pb-row-item"><button type="button" className={"pb-row pb-row-" + label.tone + (label.tone === "fail" ? " pb-row-failed" : "") + (open ? " is-open" : "")} aria-expanded={open} onClick={() => setOpenKey(open ? null : key)}>
                <span className="pb-char-cell"><span className="pb-char" lang="zh-Hant">{char}</span>{pinyin && <span className="pb-char-pinyin">{pinyin}</span>}</span>
                <span className="pb-tone-cell"><span className="pb-tone-target" aria-hidden="true">{toneArrow(syllable.tone)}</span><small>T{syllable.tone}</small><span className={"pb-mark pb-tone-mark is-" + label.tone} title={label.zh + " — " + label.en}>{label.mark}</span>{assistiveRecord?.assistive_state === "NEEDS_PRACTICE" && <span className="pb-assistive-badge" aria-hidden="true" title={ASSISTIVE_MESSAGE[assistiveRecord.assistive_state]}>◎</span>}</span>
                <span className="pb-vowel-cell"><VowelChip syllable={syllable} /></span><span className="pb-chevron" aria-hidden="true">›</span>
              </button>{open && <RowDetail syllable={syllable} word={word} referenceAccepted={accepted} debug={debug} assistiveRecord={assistiveRecord} />}</li>;
            })}</ul>
          </div>;
        })}</div>
        {hidePassed && !hasVisibleAction && <p className="pb-phrase-collapsed-note">All measured tones passed.</p>}
      </section>;
    })}</div>
    <p className="pb-footnote"><BiLabel zh="△ 表示電腦聽不太出來，不是你說錯了。母音只是量到的嘴型，沒有分數。子音（b、p、zh…）現在還量不到。" en="△ means the system could not tell, not that you were wrong. The vowel column is a measurement of your mouth shape, not a score. Initial consonants (b, p, zh …) are not measured yet." /></p>
  </section>;
}
