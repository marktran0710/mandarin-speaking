import { useEffect, useMemo, useState } from "react";
import { isProsodyHardFailure, toneArrow } from "../utils/storyRecorderFeedback";
import { primePinyin, toPinyin, toPinyinSyllables } from "../utils/pinyin";
import { scoreScriptChunks, splitTeacherScriptIntoPhrases } from "../utils/scriptAlignment";
import {
  ASSISTIVE_MESSAGE,
  matchAssistiveRecord,
  type AssistiveFeedbackSyllable,
} from "../utils/assistiveFeedback";
import { BiLabel } from "./BiLabel";
import type {
  DiagnosticStatus,
  VowelZone,
  WordProsody,
  WordProsodySyllable,
} from "./StoryRecorder";

/**
 * Character-by-character readout of what the recording actually measured.
 *
 * Built in three tiers, because the first version showed everything at once
 * and an eleven-character sentence turned into six lines of text per
 * character — technically complete, unreadable in practice:
 *
 *   1. a count summary, so the shape of the result lands in one glance;
 *   2. one legend explaining ✓ △ ✗ ↻ once, instead of repeating a bilingual
 *      label on every row;
 *   3. one line per character, with the reason, the sandhi rule and the vowel
 *      measurement behind a tap.
 *
 * Two columns, two different kinds of claim, and the difference is the point:
 *
 *  - 聲調 is a *four-state diagnosis*: CORRECT / UNCERTAIN / INCORRECT /
 *    INVALID_AUDIO. It replaced a ✓/✗ read straight off a heuristic contour
 *    score, which made "the pitch tracker had nothing to work with" look
 *    identical to "you said the wrong tone". Only INCORRECT is an accusation.
 *    This display does NOT drive lesson progression — that still runs on the
 *    legacy `passed` field, shown only in debug mode.
 *  - 母音 is a *measurement*, never a score. Formants are read from each
 *    syllable's own audio and described relative to this recording's own
 *    average, so the reading holds for any voice. See backend/vowel_analysis.py.
 *
 * Initial consonants (b/p, zh/ch/sh …) are absent because nothing in the
 * pipeline aligns them acoustically.
 */

interface BreakdownRow {
  key: string;
  char: string;
  pinyin: string;
  syllable: WordProsodySyllable;
  word: WordProsody;
}

interface BreakdownGroup {
  key: string;
  /** The word jieba segmented, e.g. 這個 — the unit practice already uses. */
  token: string;
  pinyin: string;
  rows: BreakdownRow[];
}

interface PhraseBreakdownGroup {
  key: string;
  text: string;
  words: BreakdownGroup[];
  passed: boolean | null;
  uncertain: boolean;
}

const HEIGHT_LABEL: Record<VowelZone["height"], { zh: string; en: string }> = {
  high: { zh: "嘴巴小", en: "mouth close" },
  mid: { zh: "嘴巴中", en: "mouth mid" },
  low: { zh: "嘴巴大", en: "mouth open" },
};

const BACKNESS_LABEL: Record<VowelZone["backness"], { zh: string; en: string }> = {
  front: { zh: "舌頭前", en: "tongue front" },
  central: { zh: "舌頭中", en: "tongue centre" },
  back: { zh: "舌頭後", en: "tongue back" },
};

/** One-word forms for the collapsed row, where the full phrase would not fit. */
const HEIGHT_SHORT: Record<VowelZone["height"], string> = {
  high: "小",
  mid: "中",
  low: "大",
};
const BACKNESS_SHORT: Record<VowelZone["backness"], string> = {
  front: "前",
  central: "中",
  back: "後",
};

/** Why a row has no vowel reading. Shown as the dash's tooltip so the blank is
 * never mistaken for "you got it wrong". */
const NO_VOWEL_REASON: Record<string, { zh: string; en: string }> = {
  not_applicable: {
    zh: "這個字沒有單獨的母音",
    en: "This syllable has no single vowel to measure",
  },
  no_formants: {
    zh: "這個字太短，量不到",
    en: "Too short or too quiet to measure",
  },
  not_measured: {
    zh: "這次沒有量母音",
    en: "Vowels were not measured for this attempt",
  },
};

const TONE_STATUS: Record<
  DiagnosticStatus,
  { mark: string; zh: string; en: string; tone: string }
> = {
  CORRECT: { mark: "✓", zh: "聲調對了", en: "Tone correct", tone: "pass" },
  UNCERTAIN: {
    mark: "△",
    zh: "聽不太出來",
    en: "Not clear enough to judge",
    tone: "uncertain",
  },
  // "Likely" is load-bearing. The thresholds behind this state are engineering
  // defaults that no human rater has validated, so the wording must claim
  // strong evidence of a mismatch — not an established error.
  INCORRECT: {
    mark: "✗",
    zh: "聲調可能不一樣",
    en: "Likely tone mismatch",
    tone: "fail",
  },
  INVALID_AUDIO: {
    mark: "↻",
    zh: "請再錄一次",
    en: "Could not evaluate — please record again",
    tone: "retry",
  },
};

/** Neutral tone is not an uncertain measurement — it is not a measurement at
 * all, because neutral tone has no contour target. Saying "not clear enough"
 * would imply the learner's production was borderline; it was never looked at.
 * The backend status stays UNCERTAIN for schema compatibility. */
const NEUTRAL_LABEL = {
  mark: "–",
  zh: "輕聲，不另外評分",
  en: "Neutral tone — not separately scored",
  tone: "not-measured",
};

const REASON_TEXT: Record<string, { zh: string; en: string }> = {
  neutral_tone_has_no_contour_target: {
    zh: "輕聲沒有固定的調型，所以不打分",
    en: "Neutral tone has no fixed pitch shape, so it is not scored",
  },
  segment_too_short_to_measure: {
    zh: "這個字太短，量不到調型",
    en: "This syllable was too short to measure",
  },
  insufficient_pitch_evidence: {
    zh: "這個字的聲音太少，沒辦法判斷",
    en: "Not enough voiced pitch to judge this syllable",
  },
  no_contour_measurement: {
    zh: "沒有量到調型",
    en: "No pitch measurement for this syllable",
  },
  contour_match_inconclusive: {
    zh: "調型有點接近，但不夠清楚",
    en: "The pitch movement was close but not clear",
  },
  contour_matches_expected_tone: {
    zh: "調型跟目標一樣",
    en: "The pitch moved the way this tone should",
  },
  contour_contradicts_expected_tone: {
    zh: "調型跟目標相反",
    en: "The pitch moved the opposite way from this tone",
  },
  recording_quality_unusable: {
    zh: "這次錄音沒辦法分析",
    en: "This recording could not be analysed",
  },
};

/** Human-readable label for a contextual tone rule, so a learner sees *why*
 * the target is not simply the dictionary tone. */
const RULE_TEXT: Record<string, { zh: string; en: string }> = {
  T3_T3: { zh: "三聲變調：前面那個念二聲", en: "third-tone sandhi: the first one becomes a rising tone" },
  T3_CHAIN_AMBIGUOUS_GROUPING: {
    zh: "連續三聲，兩種說法都可以",
    en: "third-tone run — either reading is accepted",
  },
  YI_SANDHI: { zh: "一 的變調", en: "一 changes tone here" },
  BU_SANDHI: { zh: "不 的變調", en: "不 changes tone here" },
  CONTEXTUAL_NEUTRAL_ALLOWED: {
    zh: "這裡念輕聲也可以",
    en: "neutral tone also accepted here",
  },
  NEUTRAL_LEXICAL: { zh: "輕聲", en: "neutral tone" },
};

/** Buckets for the summary line. Neutral is counted apart from UNCERTAIN so
 * the numbers do not imply doubt about syllables nobody measured. */
const SUMMARY_BUCKETS = [
  { key: "correct", zh: "個對了", en: "correct" },
  { key: "uncertain", zh: "個聽不太出來", en: "not clear" },
  { key: "incorrect", zh: "個要練", en: "to practise" },
  { key: "invalid", zh: "個要再錄", en: "to re-record" },
  { key: "neutral", zh: "個輕聲不計", en: "neutral, not scored" },
] as const;

function zoneText(zone: VowelZone, key: "zh" | "en"): string {
  return `${HEIGHT_LABEL[zone.height][key]}・${BACKNESS_LABEL[zone.backness][key]}`;
}

function isNeutral(syllable: WordProsodySyllable): boolean {
  return syllable.score_provenance === "neutral_not_measured";
}

function referenceEvidenceAccepted(word?: WordProsody): boolean {
  return Boolean(
    word?.reference_source === "real_voice" &&
      word.judged !== false &&
      typeof word.shape_accuracy === "number" &&
      word.shape_accuracy >= 58,
  );
}

/** A placeholder verdict is deliberately not phrase-level uncertainty. It
 * means this particular syllable was not measurable (neutral tone, too short,
 * or no score), not that every measured syllable in the phrase is doubtful. */
function hasMeasuredToneEvidence(word: WordProsody): boolean {
  return (word.syllables ?? []).some(
    (syllable) =>
      syllable.passed !== null &&
      syllable.passed !== undefined &&
      syllable.score_provenance !== "neutral_not_measured" &&
      syllable.score_provenance !== "constant_short_segment" &&
      syllable.score_provenance !== "not_scored",
  );
}

function phraseStatus(
  phraseWordRecords: WordProsody[],
): Pick<PhraseBreakdownGroup, "passed" | "uncertain"> {
  const hasHardFailure = phraseWordRecords.some(isProsodyHardFailure);
  const hasMeasuredEvidence = phraseWordRecords.some(hasMeasuredToneEvidence);
  // Neutral and unjudged syllables are not failures, and they must not
  // downgrade a phrase whose other syllables have already passed. A phrase
  // is only "not enough evidence" when it has no measured tone evidence at
  // all and no actual hard failure to show the learner.
  return {
    passed: phraseWordRecords.length === 0
      ? null
      : hasHardFailure
        ? false
        : hasMeasuredEvidence
          ? true
          : null,
    uncertain:
      phraseWordRecords.length > 0 && !hasHardFailure && !hasMeasuredEvidence,
  };
}

function statusLabel(
  syllable: WordProsodySyllable,
  referenceAccepted = false,
) {
  if (isNeutral(syllable)) return NEUTRAL_LABEL;
  const status =
    referenceAccepted && syllable.diagnostic_status === "INCORRECT"
      ? "CORRECT"
      : syllable.diagnostic_status;
  if (status) return TONE_STATUS[status];
  // Backends predating the diagnostic layer send no status. Fall back to the
  // legacy verdict rather than inventing one — a missing field must never
  // silently become "correct".
  if (syllable.passed === null || syllable.passed === undefined) {
    return TONE_STATUS.UNCERTAIN;
  }
  return syllable.passed
    ? TONE_STATUS.CORRECT
    : { ...TONE_STATUS.INCORRECT, zh: "沒過", en: "Did not pass" };
}

function breakdownGroups(words: WordProsody[]): BreakdownGroup[] {
  const groups: BreakdownGroup[] = [];
  for (const word of words) {
    const syllables = word.syllables ?? [];
    if (syllables.length === 0) continue;
    // Pinyin is looked up per word, not per character, so polyphonic
    // characters read the way they do in this word rather than in isolation.
    const pinyin = toPinyinSyllables(word.token);
    groups.push({
      key: `${word.index}-${word.token}`,
      token: word.token,
      pinyin: toPinyin(word.token),
      rows: syllables.map((syllable, index) => ({
        key: `${word.index}-${index}-${syllable.char}`,
        char: syllable.char,
        pinyin: pinyin[index] ?? "",
        syllable,
        word,
      })),
    });
  }
  return groups;
}

/** Group the existing word rows under teacher-authored phrase boundaries.
 * The acoustic rows remain word/character rows; this only changes their visual
 * hierarchy and the phrase-level content summary. */
function breakdownPhraseGroups(
  groups: BreakdownGroup[],
  targetText?: string,
  transcription?: string,
  teacherPhrases?: string[],
): PhraseBreakdownGroup[] {
  const phrases = (teacherPhrases?.length
    ? teacherPhrases
    : splitTeacherScriptIntoPhrases(targetText)
  ).filter(Boolean);
  if (phrases.length <= 1) {
    const status = phraseStatus(
      groups.flatMap((group) => group.rows.map((row) => row.word)),
    );
    return [{
      key: "phrase-0",
      text: phrases[0] ?? "",
      words: groups,
      ...status,
    }];
  }

  const words = groups.map((group) => group.rows[0]?.word).filter(Boolean);
  const scores = scoreScriptChunks(targetText, transcription, words, phrases);
  const phraseWords = phrases.map<BreakdownGroup[]>(() => []);
  const phraseIndexByWord = new Map<WordProsody, number>();
  scores.forEach((score, phraseIndex) => {
    score.tokens.forEach((word) => phraseIndexByWord.set(word, phraseIndex));
  });

  // If the transcript is unavailable, the scorer cannot align token text to a
  // phrase. Keep rows visible by assigning them in target order instead of
  // dumping every word into the first phrase.
  let fallbackPhraseIndex = 0;
  let fallbackChars = 0;
  const phraseCharCounts = phrases.map((phrase) => Array.from(phrase).filter((char) => /[\p{L}\p{N}]/u.test(char)).length);
  groups.forEach((group) => {
    const word = group.rows[0]?.word;
    let phraseIndex = word ? phraseIndexByWord.get(word) : undefined;
    if (phraseIndex === undefined) {
      const wordChars = Array.from(group.token).filter((char) => /[\p{L}\p{N}]/u.test(char)).length;
      while (
        fallbackPhraseIndex < phrases.length - 1 &&
        fallbackChars >= phraseCharCounts[fallbackPhraseIndex]
      ) {
        fallbackChars -= phraseCharCounts[fallbackPhraseIndex];
        fallbackPhraseIndex += 1;
      }
      phraseIndex = fallbackPhraseIndex;
      fallbackChars += wordChars;
    }
    phraseWords[Math.min(phraseIndex, phrases.length - 1)].push(group);
  });

  return phrases.map((text, index) => {
    const phraseWordRecords = phraseWords[index]
      .flatMap((group) => group.rows.map((row) => row.word))
      .filter(Boolean);
    const status = phraseStatus(phraseWordRecords);
    return {
      key: `phrase-${index}-${text}`,
      text,
      words: phraseWords[index],
      ...status,
    };
  });
}

function countByBucket(groups: BreakdownGroup[]): Record<string, number> {
  const counts: Record<string, number> = {
    correct: 0,
    uncertain: 0,
    incorrect: 0,
    invalid: 0,
    neutral: 0,
  };
  for (const group of groups) {
    for (const { syllable, word } of group.rows) {
      if (isNeutral(syllable)) {
        counts.neutral += 1;
        continue;
      }
      const status = statusLabel(syllable, referenceEvidenceAccepted(word));
      switch (status.tone) {
        case "pass":
          counts.correct += 1;
          break;
        case "fail":
          counts.incorrect += 1;
          break;
        case "retry":
          counts.invalid += 1;
          break;
        case "uncertain":
          counts.uncertain += 1;
          break;
        default:
          // No diagnosis: fall back to the legacy verdict so the summary still
          // adds up to the number of rows shown.
          if (syllable.passed) counts.correct += 1;
          else counts.incorrect += 1;
      }
    }
  }
  return counts;
}

/** The measured mouth shape, shortened to fit one line. */
function VowelChip({ syllable }: { syllable: WordProsodySyllable }) {
  const zone = syllable.measured_zone;
  if (!zone) {
    const status = syllable.vowel_status ?? "not_measured";
    const reason = NO_VOWEL_REASON[status] ?? NO_VOWEL_REASON.not_measured;
    return (
      <span className="pb-vowel--none" title={`${reason.zh} — ${reason.en}`}>
        —
      </span>
    );
  }
  return (
    <span className="pb-vowel-chip" lang="zh-Hant">
      嘴型 {HEIGHT_SHORT[zone.height]}・{BACKNESS_SHORT[zone.backness]}
      {syllable.vowel_status === "nucleus_only" && (
        <abbr
          className="pb-vowel-glide"
          title="這個韻母會滑動，只量中間 — this final glides, so only its middle was measured"
        >
          ~
        </abbr>
      )}
    </span>
  );
}

function RowDetail({
  syllable,
  referenceAccepted = false,
  debug,
  assistiveRecord = null,
}: {
  syllable: WordProsodySyllable;
  referenceAccepted?: boolean;
  debug: boolean;
  /** Additive ACCEPT/UNCERTAIN/NEEDS_PRACTICE record for this syllable, if
   * any -- see `PronunciationBreakdown`'s own prop doc. */
  assistiveRecord?: AssistiveFeedbackSyllable | null;
}) {
  const label = statusLabel(syllable, referenceAccepted);
  const reason =
    !referenceAccepted && !isNeutral(syllable) && syllable.diagnostic_reason
      ? REASON_TEXT[syllable.diagnostic_reason]
      : undefined;
  const rule = syllable.context_rule ? RULE_TEXT[syllable.context_rule] : undefined;
  const zone = syllable.measured_zone;

  return (
    <div className="pb-detail">
      <p className={`pb-detail-status is-${label.tone}`}>
        <span aria-hidden="true">{label.mark}</span>{" "}
        <BiLabel zh={label.zh} en={label.en} />
      </p>
      {reason && (
        <p className="pb-detail-line">
          <BiLabel zh={reason.zh} en={reason.en} />
        </p>
      )}
      {rule && (
        <p className="pb-detail-line pb-detail-rule">
          <BiLabel zh={rule.zh} en={rule.en} />
        </p>
      )}
      {assistiveRecord && assistiveRecord.assistive_state !== "ACCEPT" && (
        <p className="pb-detail-line pb-detail-assistive" data-assistive-state={assistiveRecord.assistive_state}>
          {ASSISTIVE_MESSAGE[assistiveRecord.assistive_state]}
        </p>
      )}

      {zone && (
        <div className="pb-detail-vowel">
          {syllable.expected_vowel && (
            <p className="pb-detail-line">
              <span className="pb-detail-label" lang="zh-Hant">
                要說
              </span>{" "}
              <em>{syllable.expected_vowel === "v" ? "ü" : syllable.expected_vowel}</em>{" "}
              {syllable.expected_zone && (
                <span lang="zh-Hant">{zoneText(syllable.expected_zone, "zh")}</span>
              )}
            </p>
          )}
          <p className="pb-detail-line">
            <span className="pb-detail-label" lang="zh-Hant">
              你說
            </span>{" "}
            <span lang="zh-Hant">{zoneText(zone, "zh")}</span>
            <small lang="en">
              {" "}
              — {zoneText(zone, "en")}
              {(syllable.f1 ?? 0) > 0 && (
                <>
                  {" "}
                  · F1 {Math.round(syllable.f1 ?? 0)} · F2{" "}
                  {Math.round(syllable.f2 ?? 0)} Hz
                </>
              )}
            </small>
          </p>
        </div>
      )}

      {/* Research/debug only. The raw number is a heuristic contour match, not
          a probability and not a pronunciation score out of 100 — showing it
          to a learner invites exactly that misreading. */}
      {debug && (
        <p className="pb-detail-debug">
          Contour match: {syllable.contour_match_score ?? "—"}/100 · provenance:{" "}
          {syllable.score_provenance ?? "unknown"} · legacy gate:{" "}
          {syllable.legacy?.passed === true
            ? "PASS"
            : syllable.legacy?.passed === false
              ? "FAIL"
              : "n/a"}{" "}
          ({syllable.legacy?.score ?? syllable.score} vs{" "}
          {syllable.legacy?.threshold ?? 58})
        </p>
      )}
    </div>
  );
}

export default function PronunciationBreakdown({
  words,
  targetText,
  transcription,
  teacherPhrases,
  debug = false,
  assistiveFeedback = null,
}: {
  words: WordProsody[];
  /** Teacher's full scene sentence, used only to establish phrase context. */
  targetText?: string;
  /** Student transcript, used to assign word rows to teacher phrases. */
  transcription?: string;
  /** Explicit teacher phrase boundaries. If omitted, punctuation in targetText
   * is used and an unpunctuated sentence remains one phrase. */
  teacherPhrases?: string[];
  /** Research/teacher mode: reveals the raw contour-match number, its
   * provenance, and the legacy progression gate. Off for learners. */
  debug?: boolean;
  /** Additive ACCEPT/UNCERTAIN/NEEDS_PRACTICE layer, matched to rows by
   * position (one record per Han character, same order this component
   * already flattens `words` into) with a character sanity check -- see
   * `matchAssistiveRecord`. `null`/absent unless the backend has the
   * assistive-feedback flag enabled; every row simply shows nothing extra
   * in that case. */
  assistiveFeedback?: AssistiveFeedbackSyllable[] | null;
}) {
  const [openKey, setOpenKey] = useState<string | null>(null);
  const pinyinTokens = useMemo(
    () => [...new Set(
      words
        .map((word) => word.token.trim())
        .filter((token) => /[\u3400-\u9fff]/u.test(token)),
    )],
    [words],
  );
  const pinyinQuery = pinyinTokens.join("\u0000");
  const [pinyinRevision, setPinyinRevision] = useState(0);
  useEffect(() => {
    let active = true;
    if (pinyinTokens.length > 0) {
      void primePinyin(pinyinTokens)
        .then(() => {
          if (active) setPinyinRevision((revision) => revision + 1);
        })
        .catch(() => {
          // The breakdown remains useful without pinyin when the backend is
          // temporarily unavailable. The next analysis retries this query.
        });
    }
    return () => {
      active = false;
    };
  }, [pinyinQuery]);
  const groups = useMemo(
    () => breakdownGroups(words),
    [words, pinyinRevision],
  );
  if (groups.length === 0) return null;
  const phraseGroups = breakdownPhraseGroups(
    groups,
    targetText,
    transcription,
    teacherPhrases,
  );
  let flatIndex = -1;

  const counts = countByBucket(groups);
  const summary = SUMMARY_BUCKETS.filter((bucket) => counts[bucket.key] > 0);

  return (
    <section className="pronunciation-breakdown" aria-label="Pronunciation breakdown">
      <div className="pb-head">
        <p className="block-label pb-heading">
          <BiLabel zh="發音分析" pinyin="Fāyīn fēnxī" en="Pronunciation breakdown" />
        </p>
        {summary.length > 0 && (
          <p className="pb-summary">
            {summary.map((bucket, index) => (
              <span key={bucket.key} className={`pb-summary-item is-${bucket.key}`}>
                {index > 0 && <span aria-hidden="true"> · </span>}
                <strong>{counts[bucket.key]}</strong>
                <span lang="zh-Hant">{bucket.zh}</span>
                <small lang="en">{bucket.en}</small>
              </span>
            ))}
          </p>
        )}
      </div>

      {/* The legend replaces a bilingual status label on every single row. */}
      <ul className="pb-legend">
        {(["CORRECT", "UNCERTAIN", "INCORRECT", "INVALID_AUDIO"] as const).map(
          (status) => (
            <li key={status} className={`pb-legend-item is-${TONE_STATUS[status].tone}`}>
              <span className="pb-mark" aria-hidden="true">
                {TONE_STATUS[status].mark}
              </span>
              <BiLabel zh={TONE_STATUS[status].zh} en={TONE_STATUS[status].en} />
            </li>
          ),
        )}
      </ul>

      <div className="pb-groups">
        {phraseGroups.map((phrase) => (
          <section
            className={`pb-phrase-group${phrase.text ? "" : " is-unstructured"}`}
            key={phrase.key}
          >
            {phrase.text && (
              <div className="pb-phrase-header">
                <span className="pb-phrase-label" lang="zh-Hant">{phrase.text}</span>
                <span className="pb-phrase-note">
                  {phrase.uncertain
                    ? "not enough evidence"
                    : phrase.passed === true
                      ? "phrase ready"
                      : phrase.passed === false
                        ? "needs practice"
                        : "word detail"}
                </span>
              </div>
            )}
            <div className="pb-phrase-words">
            {phrase.words.map((group) => (
          <div className="pb-group" key={group.key}>
            <p className="pb-group-header">
              <span className="pb-group-token" lang="zh-Hant">
                {group.token}
              </span>
              {group.pinyin && (
                <span className="pb-group-pinyin">{group.pinyin}</span>
              )}
            </p>

            <ul className="pb-rows">
              {group.rows.map(({ key, char, pinyin, syllable, word }) => {
                flatIndex += 1;
                const assistiveRecord = matchAssistiveRecord(assistiveFeedback, flatIndex, char);
                const referenceAccepted = referenceEvidenceAccepted(word);
                const label = statusLabel(syllable, referenceAccepted);
                // Only a confident error gets the red field. An △ must never
                // read as a mistake — that conflation is the bug this replaced.
                const failed = label.tone === "fail";
                const open = openKey === key;

                return (
                  <li key={key} className="pb-row-item">
                    <button
                      type="button"
                      className={`pb-row${failed ? " pb-row-failed" : ""}${open ? " is-open" : ""}`}
                      aria-expanded={open}
                      onClick={() => setOpenKey(open ? null : key)}
                    >
                      <span className="pb-char-cell">
                        <span className="pb-char" lang="zh-Hant">
                          {char}
                        </span>
                        {pinyin && <span className="pb-char-pinyin">{pinyin}</span>}
                      </span>

                      <span className="pb-tone-cell">
                        <span className="pb-tone-target" aria-hidden="true">
                          {toneArrow(syllable.tone)}
                        </span>
                        <small>T{syllable.tone}</small>
                        <span
                          className={`pb-mark pb-tone-mark is-${label.tone}`}
                          title={`${label.zh} — ${label.en}`}
                        >
                          {label.mark}
                        </span>
                        {assistiveRecord && assistiveRecord.assistive_state === "NEEDS_PRACTICE" && (
                          <span
                            className="pb-assistive-badge"
                            aria-hidden="true"
                            title={ASSISTIVE_MESSAGE[assistiveRecord.assistive_state]}
                          >
                            ◎
                          </span>
                        )}
                      </span>

                      <span className="pb-vowel-cell">
                        <VowelChip syllable={syllable} />
                      </span>

                      <span className="pb-chevron" aria-hidden="true">
                        ›
                      </span>
                    </button>
                    {open && (
                      <RowDetail
                        syllable={syllable}
                        referenceAccepted={referenceAccepted}
                        debug={debug}
                        assistiveRecord={assistiveRecord}
                      />
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
            </div>
          </section>
        ))}
      </div>

      <p className="pb-footnote">
        <BiLabel
          zh="△ 表示電腦聽不太出來，不是你說錯了。母音只是量到的嘴型，沒有分數。子音（b、p、zh…）現在還量不到。"
          en="△ means the system could not tell, not that you were wrong. The vowel column is a measurement of your mouth shape, not a score. Initial consonants (b, p, zh …) are not measured yet."
        />
      </p>
    </section>
  );
}
