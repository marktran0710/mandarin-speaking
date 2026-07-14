import { scoreTier, scoreTierLabel } from "../utils/scoreLabels";
import {
  TONE_NUMBER_ARROW_LABEL,
  TONE_NUMBER_TO_SHAPE,
  TONE_SHAPES,
  averageWordProsodyAccuracy,
  isContentAccepted,
  weakToneGuideItems,
} from "../utils/storyRecorderFeedback";
import type { PraatMetrics } from "./StoryRecorder";
import { BiLabel, BiText } from "./BiLabel";

// ─── Learning Scaffold ────────────────────────────────────────────────────────

export default function FeedbackSummary({
  praatMetrics,
  attemptHistory,
  transcription,
}: {
  praatMetrics: PraatMetrics;
  attemptHistory: Array<{ tone: number; fluency: number; attempt: number }>;
  transcription: string;
}) {
  const ai = praatMetrics.ai_feedback;
  const vocabScore = ai?.vocabulary_coverage?.score ?? null;
  const pronScore = averageWordProsodyAccuracy(praatMetrics.word_prosody);
  const toneScore = Math.round(praatMetrics.tone_accuracy);
  const contentAccuracy = ai?.content_accuracy;
  // Only a real score when a vision-capable engine actually judged it —
  // otherwise it's a 0 placeholder (e.g. Groq/local can't see the image)
  // that would misleadingly render as a failing score bar.
  const contentScore = contentAccuracy?.judged ? contentAccuracy.score : null;

  const missingVocab = (ai?.vocabulary_coverage?.missing?.length ?? 0) > 0;
  const vocabListExists = ai?.vocabulary_coverage !== undefined;

  const contentAccepted = isContentAccepted(praatMetrics);
  const weakToneItems = weakToneGuideItems(praatMetrics.word_prosody || []);

  const overallScore =
    vocabScore !== null && pronScore !== null
      ? Math.round((vocabScore + pronScore + toneScore) / 3)
      : toneScore;

  const overallLabel = !contentAccepted
    ? "先確認句子的意思 Check your sentence's meaning first"
    : vocabListExists && missingVocab
      ? "先使用所有詞彙 Use all vocab first"
      : overallScore >= 85
        ? "太棒了！ Excellent!"
        : overallScore >= 70
          ? "進步良好 Good progress"
          : "繼續加油 Keep going";

  const prev =
    attemptHistory.length > 1
      ? attemptHistory[attemptHistory.length - 2]
      : null;
  const curr =
    attemptHistory.length > 0
      ? attemptHistory[attemptHistory.length - 1]
      : null;
  const trendDiff = prev && curr ? curr.tone - prev.tone : null;

  return (
    <div className="feedback-summary">
      <div className="feedback-summary-top">
        <div className="feedback-summary-score">
          <span className="feedback-summary-number">{overallScore}</span>
          <span className="feedback-summary-denom">/100</span>
        </div>
        <div className="feedback-summary-meta">
          <p className="feedback-summary-label">{overallLabel}</p>
          <p className="feedback-summary-attempt">
            <BiLabel
              zh={`第 ${attemptHistory.length || 1} 次`}
              pinyin={`Dì ${attemptHistory.length || 1} cì`}
              en={`Attempt ${attemptHistory.length || 1}`}
            />
          </p>
          {trendDiff !== null && (
            <p
              className={`feedback-summary-trend ${trendDiff > 0 ? "up" : trendDiff < 0 ? "down" : ""}`}
            >
              {trendDiff > 0 ? (
                <BiLabel
                  zh={`↑ 比上次 +${trendDiff}%`}
                  pinyin={`↑ bǐ shàngcì +${trendDiff}%`}
                  en={`↑ +${trendDiff}% from last try`}
                />
              ) : trendDiff < 0 ? (
                <BiLabel
                  zh={`↓ ${trendDiff}% — 繼續加油`}
                  pinyin={`↓ ${trendDiff}% — jìxù jiāyóu`}
                  en={`↓ ${trendDiff}% — keep going`}
                />
              ) : (
                <BiLabel k="same_as_last_try" />
              )}
            </p>
          )}
        </div>
      </div>

      {transcription && (
        <p className="feedback-summary-transcript">
          <BiLabel k="you_said" /> <em lang="zh-TW">"{transcription}"</em>
        </p>
      )}

      {/* ── Meaning check comes first: does the sentence actually fit the picture? ── */}
      {/* judged:true means a vision model actually evaluated it; false = placeholder */}
      {contentAccuracy?.judged && contentAccuracy.feedback && (
        <div
          className={`content-accuracy-panel ${contentAccepted ? "is-accepted" : "is-rejected"}`}
        >
          <p className="score-guide-heading">
            <BiLabel k="does_it_match_the_image" />
          </p>
          <p className="content-accuracy-feedback">
            {contentAccuracy.feedback}
          </p>
          {contentAccuracy.matched_details.length > 0 && (
            <p className="content-accuracy-matched">
              ✓ {contentAccuracy.matched_details.join(", ")}
            </p>
          )}
          {contentAccuracy.missed_details.length > 0 && (
            <p className="content-accuracy-missed">
              ✗ {contentAccuracy.missed_details.join(", ")}
            </p>
          )}
          {!contentAccepted && (
            <p className="content-accuracy-gate-hint">
              <BiLabel
                zh="先改對句子的意思，再看發音回饋。"
                pinyin="Xiān gǎi duì jùzi de yìsi, zài kàn fāyīn huíkuì."
                en="Fix what your sentence means first — pronunciation feedback comes after that."
              />
            </p>
          )}
        </div>
      )}

      {/* ── Pronunciation feedback only once the meaning is accepted ── */}
      {contentAccepted && (
        <>
          {(() => {
            const bars = [
              ...(vocabScore !== null
                ? [
                    {
                      label: "詞彙 Vocabulary",
                      score: vocabScore,
                      color: "var(--seal)",
                      isPraatTone: false,
                    },
                  ]
                : []),
              {
                label: "聲調 Tone accuracy",
                score: toneScore,
                color: "var(--gold)",
                isPraatTone: true,
              },
              ...(contentScore !== null
                ? [
                    {
                      label: "內容準確度 Content accuracy",
                      score: contentScore,
                      color: "var(--jade)",
                      isPraatTone: false,
                    },
                  ]
                : []),
            ];
            return bars.length > 0 ? (
              <div className="feedback-summary-bars">
                {bars.map(({ label, score, color, isPraatTone }) => (
                  <div key={label} className="feedback-summary-bar-card">
                    <span className="feedback-summary-bar-label">{label}</span>
                    <span
                      className={
                        isPraatTone
                          ? `feedback-summary-bar-pct score-tier-text ${scoreTier(score)}`
                          : "feedback-summary-bar-pct"
                      }
                      style={isPraatTone ? undefined : { color }}
                    >
                      {isPraatTone ? (
                        scoreTierLabel(scoreTier(score)).zh
                      ) : (
                        `${score}%`
                      )}
                    </span>
                    <div className="feedback-summary-bar-track">
                      <div
                        className="feedback-summary-bar-fill"
                        style={{ width: `${score}%`, background: color }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            ) : null;
          })()}

          {toneScore > 0 && (
            <div className="score-guide">
              <p className="score-guide-heading">
                <BiLabel k="how_to_reach_100" />
              </p>
              <div className="score-guide-rows">
                {toneScore < 100 && (
                  <div className="score-guide-row">
                    <span className="score-guide-label">
                      <BiLabel k="tone_accuracy" />
                    </span>
                    <ul className="score-guide-tips">
                      {weakToneItems.length > 0 ? (
                        <>
                          {weakToneItems.map((item) => {
                            const tone = item.expected_tones![0];
                            const shapeKey =
                              TONE_NUMBER_TO_SHAPE[tone] ?? "variable";
                            return (
                              <li key={`${item.token}-${item.index}`}>
                                <strong>
                                  「{item.token}」{" "}
                                  {TONE_NUMBER_ARROW_LABEL[tone] ?? ""}
                                </strong>{" "}
                                {TONE_SHAPES[shapeKey].tip} (
                                <span className={`score-tier-text ${scoreTier(item.tone_accuracy ?? 0)}`}>
                                  {scoreTierLabel(scoreTier(item.tone_accuracy ?? 0)).zh}
                                </span>
                                )
                              </li>
                            );
                          })}
                          <li>
                            <BiText k="isolate_problem_characters_from_the_tone" />
                          </li>
                        </>
                      ) : (
                        <>
                          <li>
                            <strong>一聲 Tone 1 (ā) →</strong>{" "}
                            <BiText k="keep_pitch_high_and_completely_flat_thro" />
                          </li>
                          <li>
                            <strong>二聲 Tone 2 (á) ↗</strong>{" "}
                            <BiText k="start_mid_push_pitch_up_to_the_top_like_" />
                          </li>
                          <li>
                            <strong>三聲 Tone 3 (ǎ) ↘↗</strong>{" "}
                            <BiText k="dip_down_first_then_rise_back_the_lowest" />
                          </li>
                          <li>
                            <strong>四聲 Tone 4 (à) ↘</strong>{" "}
                            <BiText k="start_as_high_as_you_can_and_drop_sharpl" />
                          </li>
                          <li>
                            <BiText k="isolate_problem_characters_from_the_tone" />
                          </li>
                        </>
                      )}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
