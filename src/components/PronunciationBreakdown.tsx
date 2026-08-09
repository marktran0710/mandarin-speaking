import { toneArrow } from "../utils/storyRecorderFeedback";
import { toPinyin, toPinyinSyllables } from "../utils/pinyin";
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
 * This exists because the per-syllable analysis was already being computed and
 * then shown to almost nobody: it only surfaced inside the practice step, only
 * for words that had failed, and only one word at a time. A student who read
 * the sentence well saw no breakdown at all, which reads as "the app didn't
 * listen".
 *
 * Two columns, two different kinds of claim, and the difference is the whole
 * point:
 *
 *  - 聲調 is a *four-state diagnosis*: CORRECT / UNCERTAIN / INCORRECT /
 *    INVALID_AUDIO. It replaced a ✓/✗ read straight off a heuristic contour
 *    score, which made "the pitch tracker had nothing to work with" look
 *    identical to "you said the wrong tone". Only INCORRECT is an accusation.
 *    Note this display does NOT drive lesson progression — that still runs on
 *    the legacy `passed` field, unchanged, and is shown only in debug mode.
 *  - 母音 is a *measurement*. Formants are read from each syllable's own slice
 *    of audio and described relative to this recording's own average — never
 *    against a fixed table, which would misjudge any voice smaller than an
 *    adult's. There is deliberately no right/wrong on it: a beginner sentence
 *    does not contain enough distinct vowels to normalise a speaker reliably,
 *    and a confident wrong verdict is worse than none. See
 *    backend/vowel_analysis.py for the full reasoning.
 *
 * Initial consonants (b/p, zh/ch/sh …) are absent because nothing in the
 * pipeline aligns them acoustically. An earlier experimental panel printed
 * them from evenly-divided timings; that was removed rather than shown.
 */

interface BreakdownRow {
  key: string;
  char: string;
  pinyin: string;
  syllable: WordProsodySyllable;
}

interface BreakdownGroup {
  key: string;
  /** The word jieba segmented, e.g. 這個 — the unit practice already uses. */
  token: string;
  pinyin: string;
  /** Legacy whole-word verdict; null when the analyzer could not judge it. */
  passed?: boolean | null;
  /** Word-level four-state diagnosis, independent of `passed`. */
  diagnostic?: DiagnosticStatus;
  rows: BreakdownRow[];
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

/** The four tone states, as a learner should read them.
 *
 * The old display collapsed everything into ✓/✗ off a single heuristic
 * score, so "the pitch tracker had nothing to work with" and "you said the
 * wrong tone" looked identical — both red. These four say which one it is,
 * and only one of them is an accusation. */
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
  // "Likely" is load-bearing. The thresholds behind this state are
  // engineering defaults that no human rater has validated, so the wording
  // must claim strong evidence of a mismatch — not an established error.
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

/** Why the system could not decide, in words a beginner can act on. Keyed by
 * the backend's stable reason codes. */
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
  recording_quality_unusable: {
    zh: "這次錄音沒辦法分析",
    en: "This recording could not be analysed",
  },
};

/** Human-readable label for a contextual tone rule, so a learner sees *why*
 * the target is not simply the dictionary tone. */
const RULE_TEXT: Record<string, { zh: string; en: string }> = {
  T3_T3: { zh: "三聲變調", en: "third-tone sandhi" },
  T3_CHAIN_AMBIGUOUS_GROUPING: {
    zh: "連續三聲，兩種說法都可以",
    en: "third-tone run — either reading is accepted",
  },
  YI_SANDHI: { zh: "一 的變調", en: "一 tone change" },
  BU_SANDHI: { zh: "不 的變調", en: "不 tone change" },
  CONTEXTUAL_NEUTRAL_ALLOWED: {
    zh: "這裡念輕聲也可以",
    en: "neutral tone also accepted here",
  },
  NEUTRAL_LEXICAL: { zh: "輕聲", en: "neutral tone" },
};

function zoneText(zone: VowelZone, key: "zh" | "en"): string {
  return `${HEIGHT_LABEL[zone.height][key]}・${BACKNESS_LABEL[zone.backness][key]}`;
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
      // Verdict only, deliberately no word-level percentage. The word score
      // is a whole-word shape similarity while the syllable scores below are
      // directional reads, so the two numbers legitimately disagree — 週末
      // scored 35 % sitting above 週 100 % and 末 69 % just looked broken.
      // The tick is safe to show because it *is* the min-rule over exactly
      // the syllables printed underneath it.
      passed: word.passed,
      diagnostic: word.diagnostic_status,
      rows: syllables.map((syllable, index) => ({
        key: `${word.index}-${index}-${syllable.char}`,
        char: syllable.char,
        pinyin: pinyin[index] ?? "",
        syllable,
      })),
    });
  }
  return groups;
}

function ToneCell({
  syllable,
  debug,
}: {
  syllable: WordProsodySyllable;
  debug: boolean;
}) {
  // Backends predating this patch send no diagnosis. Rather than inventing
  // one, fall back to the legacy verdict and say plainly that it is the old
  // pass/fail — a missing field must not silently become "correct".
  const status = syllable.diagnostic_status;
  // A neutral-tone syllable is not an uncertain measurement — it is not a
  // measurement at all, because neutral tone has no contour target. Saying
  // "not clear enough to judge" would imply the learner's production was
  // borderline. It wasn't looked at. The status stays UNCERTAIN for schema
  // compatibility; only the wording differs.
  const notMeasured = syllable.score_provenance === "neutral_not_measured";
  const label = notMeasured
    ? {
        mark: "–",
        zh: "輕聲，不另外評分",
        en: "Neutral tone — not separately scored",
        tone: "not-measured",
      }
    : status
      ? TONE_STATUS[status]
      : null;
  const reason =
    !notMeasured && syllable.diagnostic_reason
      ? REASON_TEXT[syllable.diagnostic_reason]
      : undefined;
  const rule = syllable.context_rule ? RULE_TEXT[syllable.context_rule] : undefined;

  // Only a confident error gets the red field. An △ must never read as a
  // mistake — that conflation is the entire bug this replaced.
  const failed = status
    ? status === "INCORRECT"
    : syllable.passed === false;

  return (
    <td className={`pb-tone-cell${failed ? " pb-tone-failed" : ""}`}>
      <span className="pb-tone-target">
        {toneArrow(syllable.tone)}
        <small>T{syllable.tone}</small>
      </span>

      {label ? (
        <span className={`pb-tone-verdict is-${label.tone}`}>
          <span className="pb-tone-mark" aria-hidden="true">
            {label.mark}
          </span>
          <BiLabel zh={label.zh} en={label.en} />
        </span>
      ) : (
        <span
          className={`pb-tone-verdict ${syllable.passed ? "is-pass" : "is-fail"}`}
        >
          {syllable.passed ? "✓" : "✗"}
        </span>
      )}

      {reason && (
        <small className="pb-tone-reason">
          <BiLabel zh={reason.zh} en={reason.en} />
        </small>
      )}
      {rule && (
        <small className="pb-tone-rule">
          <BiLabel zh={rule.zh} en={rule.en} />
        </small>
      )}

      {/* Research/debug only. The raw number is a heuristic contour match, not
          a probability and not a pronunciation score out of 100 — showing it
          to a learner invites exactly that misreading, so it stays behind the
          debug flag together with the legacy gate it feeds. */}
      {debug && (
        <small className="pb-tone-debug">
          Contour match: {syllable.contour_match_score ?? "—"}/100 ·{" "}
          provenance: {syllable.score_provenance ?? "unknown"} · legacy gate:{" "}
          {syllable.legacy?.passed === true
            ? "PASS"
            : syllable.legacy?.passed === false
              ? "FAIL"
              : "n/a"}{" "}
          ({syllable.legacy?.score ?? syllable.score} vs{" "}
          {syllable.legacy?.threshold ?? 58})
        </small>
      )}
    </td>
  );
}

function VowelCell({ syllable }: { syllable: WordProsodySyllable }) {
  const status = syllable.vowel_status ?? "not_measured";
  const zone = syllable.measured_zone;

  if (!zone) {
    const reason = NO_VOWEL_REASON[status] ?? NO_VOWEL_REASON.not_measured;
    return (
      <span className="pb-vowel pb-vowel--none" title={`${reason.zh} — ${reason.en}`}>
        —
      </span>
    );
  }

  // The glide caveat applies to most finals, so it rides as a marker on the
  // row rather than a sentence repeated down the whole column; the footnote
  // carries the full explanation once.
  const glides = status === "nucleus_only";

  return (
    <span className="pb-vowel">
      {syllable.expected_vowel && (
        <span className="pb-vowel-line">
          <span className="pb-vowel-label" lang="zh-Hant">
            要說
          </span>
          <em>{syllable.expected_vowel === "v" ? "ü" : syllable.expected_vowel}</em>
          {syllable.expected_zone && (
            <span className="pb-vowel-zone" lang="zh-Hant">
              {zoneText(syllable.expected_zone, "zh")}
            </span>
          )}
        </span>
      )}
      <span className="pb-vowel-line">
        <span className="pb-vowel-label" lang="zh-Hant">
          你說
        </span>
        <span className="pb-vowel-zone" lang="zh-Hant">
          {zoneText(zone, "zh")}
        </span>
        {glides && (
          <abbr
            className="pb-vowel-glide"
            title="這個韻母會滑動，只量中間 — this final glides, so only its middle was measured"
          >
            ~
          </abbr>
        )}
      </span>
      <small className="pb-vowel-en" lang="en">
        You said: {zoneText(zone, "en")}
        {(syllable.f1 ?? 0) > 0 && (
          <> · F1 {Math.round(syllable.f1 ?? 0)} · F2 {Math.round(syllable.f2 ?? 0)} Hz</>
        )}
      </small>
    </span>
  );
}

export default function PronunciationBreakdown({
  words,
  debug = false,
}: {
  words: WordProsody[];
  /** Research/teacher mode: reveals the raw contour-match number, its
   * provenance, and the legacy progression gate. Off for learners. */
  debug?: boolean;
}) {
  const groups = breakdownGroups(words);
  if (groups.length === 0) return null;

  return (
    <section className="pronunciation-breakdown" aria-label="Pronunciation breakdown">
      <p className="block-label pb-heading">
        <BiLabel zh="發音分析" pinyin="Fāyīn fēnxī" en="Pronunciation breakdown" />
      </p>

      <div className="pb-scroll">
        <table className="pb-table">
          <thead>
            <tr>
              <th scope="col">
                <BiLabel zh="字" en="Character" />
              </th>
              <th scope="col">
                <BiLabel zh="聲調" pinyin="Shēngdiào" en="Tone" />
              </th>
              <th scope="col">
                <BiLabel zh="母音" pinyin="Mǔyīn" en="Vowel" />
              </th>
            </tr>
          </thead>
          {/* One tbody per word, so the table reads as the phrases the
              student actually practises (這個, 週末) rather than a flat run of
              characters. The group header carries the word's own verdict —
              the same one that drives the practice list. */}
          {groups.map((group) => (
            <tbody key={group.key} className="pb-group">
              <tr className="pb-group-row">
                <th scope="colgroup" colSpan={3} className="pb-group-header">
                  <span className="pb-group-token" lang="zh-Hant">
                    {group.token}
                  </span>
                  {group.pinyin && (
                    <span className="pb-group-pinyin">{group.pinyin}</span>
                  )}
                  {group.diagnostic ? (
                    <span
                      className={`pb-group-verdict is-${TONE_STATUS[group.diagnostic].tone}`}
                      title={TONE_STATUS[group.diagnostic].en}
                    >
                      {TONE_STATUS[group.diagnostic].mark}
                    </span>
                  ) : (
                    group.passed != null && (
                      <span
                        className={`pb-group-verdict ${group.passed ? "is-pass" : "is-fail"}`}
                      >
                        {group.passed ? "✓" : "✗"}
                      </span>
                    )
                  )}
                </th>
              </tr>
              {group.rows.map(({ key, char, pinyin, syllable }) => (
              <tr key={key}>
                <th scope="row" className="pb-char-cell">
                  <span className="pb-char" lang="zh-Hant">
                    {char}
                  </span>
                  {pinyin && <span className="pb-char-pinyin">{pinyin}</span>}
                </th>
                {/* Only the tone cell carries the failed tint. Tinting the
                    whole row would drag the vowel column into a verdict it
                    does not make. */}
                <ToneCell syllable={syllable} debug={debug} />
                <td className="pb-vowel-cell">
                  <VowelCell syllable={syllable} />
                </td>
              </tr>
              ))}
            </tbody>
          ))}
        </table>
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
