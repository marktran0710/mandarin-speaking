import { useEffect, useRef, useState } from "react";
import { BiLabel } from "./BiLabel";
import RecordingPlayback from "./RecordingPlayback";
import WordProsodyCard from "./WordProsodyCard";
import {
  failedProsodyWords,
  isContentAccepted,
  weakToneGuideItems,
} from "../utils/storyRecorderFeedback";
import type { PraatMetrics, Topic } from "./StoryRecorder";
import { toPinyin } from "../utils/pinyin";

// Labels for pronunciation_note.details — one line per aspect inside the
// overview step's 發音回饋 panel.
const PRONUNCIATION_DETAIL_LABELS: Record<
  string,
  { icon: string; zh: string; pinyin: string; en: string }
> = {
  tone: { icon: "🎵", zh: "聲調", pinyin: "Shēngdiào", en: "Tone" },
  rhythm_pace: { icon: "⏱️", zh: "節奏和速度", pinyin: "Jiézòu hé sùdù", en: "Rhythm & Pace" },
  pausing: { icon: "⏸️", zh: "停頓", pinyin: "Tíngdùn", en: "Pausing" },
  vowel_quality: { icon: "👄", zh: "母音", pinyin: "Mǔyīn", en: "Vowel Quality" },
  word_stress: { icon: "💪", zh: "重音", pinyin: "Zhòngyīn", en: "Word Stress" },
};

type ResultsStep = "overview" | "fix" | "practice";

const STEP_LABELS: Record<ResultsStep, { zh: string; en: string }> = {
  overview: { zh: "結果", en: "Results" },
  fix: { zh: "改句子", en: "Fix it" },
  practice: { zh: "練習", en: "Practice" },
};

interface SpeakingResultsFlowProps {
  selectedImage: string;
  selectedImageIndex: number;
  totalScenes: number;
  narrativeMode: Topic["narrativeMode"];
  attempts: number;
  /** Scene unlocked (score/attempts rule AND pronunciation mastery). */
  ready: boolean;
  masteryPassed: boolean;
  praatMetrics: PraatMetrics;
  analysisAudioBlob: Blob | null;
  submittedAudioName: string;
  clearedWords: string[];
  onWordDrillPass: (token: string) => void;
  hasNextScene: boolean;
  onNextScene: () => void;
  onViewSummary: () => void;
  onRecordAgain: () => void;
}

/** The results half of the Speaking step, as a guided mini-flow instead of
 * one dense readout:
 *
 *   [1] overview — verdict, playback, stats, overall pronunciation notes
 *   [2] fix      — meaning correction + missing vocabulary (only when needed)
 *   [3] practice — one failed word at a time, weakest first, drill in place
 *
 * Steps are adaptive: a step that has nothing to show doesn't exist (not
 * "disabled"). Forward movement goes through each step's CTA; any step
 * already visited can be revisited from the stepper. The parent remounts
 * this component (key) per new analysis, which resets the flow to step 1. */
export default function SpeakingResultsFlow({
  selectedImage,
  selectedImageIndex,
  totalScenes,
  narrativeMode,
  attempts,
  ready,
  masteryPassed,
  praatMetrics,
  analysisAudioBlob,
  submittedAudioName,
  clearedWords,
  onWordDrillPass,
  hasNextScene,
  onNextScene,
  onViewSummary,
  onRecordAgain,
}: SpeakingResultsFlowProps) {
  const ai = praatMetrics.ai_feedback;
  const accepted = isContentAccepted(praatMetrics);
  const vocabCoverage = ai?.vocabulary_coverage;
  const missing = vocabCoverage?.missing ?? [];
  const usedCount = vocabCoverage?.used?.length ?? 0;
  const vocabTotal = usedCount + missing.length;
  const weakItems = weakToneGuideItems(praatMetrics.word_prosody || []);
  const contentAccuracy = ai?.content_accuracy;
  const corrective = ai?.corrective_feedback;
  const pronunciationNote = ai?.pronunciation_note;
  const meaningJudged = Boolean(contentAccuracy?.judged);

  const failedWords = failedProsodyWords(praatMetrics.word_prosody);
  // Practice order: weakest shape first — the word the student most needs
  // is the first one the focus view lands on.
  const practiceWords = [...failedWords].sort(
    (a, b) =>
      (a.shape_accuracy ?? a.tone_accuracy ?? 0) -
      (b.shape_accuracy ?? b.tone_accuracy ?? 0),
  );
  const remainingDrillWords = practiceWords.filter(
    (word) => !clearedWords.includes(word.token),
  );
  const allDrillsCleared =
    practiceWords.length > 0 && remainingDrillWords.length === 0;

  // The one-verdict ladder: meaning gates everything, then the unlock
  // state, then vocabulary, then pronunciation polish.
  const verdict: "meaning" | "ready" | "vocab" | "pronounce" = !accepted
    ? "meaning"
    : ready
      ? "ready"
      : missing.length > 0
        ? "vocab"
        : "pronounce";

  const showCorrective =
    narrativeMode !== "listen_retell" &&
    !(accepted && missing.length === 0) &&
    corrective &&
    (corrective.errors.length > 0 || corrective.hint || corrective.correct_version);

  // Adaptive step list. A meaning failure never leads to word practice —
  // drilling pronunciation of a sentence that means the wrong thing is
  // wasted effort, so the flow stops at "fix it" and points back to record.
  const hasFix = !accepted || missing.length > 0;
  const hasPractice = accepted && practiceWords.length > 0;
  const steps: ResultsStep[] = [
    "overview",
    ...(hasFix ? (["fix"] as const) : []),
    ...(hasPractice ? (["practice"] as const) : []),
  ];

  const [step, setStep] = useState<ResultsStep>("overview");
  const [maxVisited, setMaxVisited] = useState(0);
  const goToStep = (target: ResultsStep) => {
    const index = steps.indexOf(target);
    if (index === -1) return;
    setStep(target);
    setMaxVisited((prev) => Math.max(prev, index));
  };

  // Focus-mode pointer into practiceWords — starts on the weakest word the
  // student hasn't already drilled back to a pass.
  const [focusIndex, setFocusIndex] = useState(() => {
    const first = practiceWords.findIndex(
      (word) => !clearedWords.includes(word.token),
    );
    return first === -1 ? 0 : first;
  });
  const focusWord = practiceWords[focusIndex];

  // After a drill pass, linger briefly so the student sees their ✓ result,
  // then move focus to the next word still waiting.
  const advanceTimer = useRef<number | null>(null);
  useEffect(
    () => () => {
      if (advanceTimer.current !== null) {
        window.clearTimeout(advanceTimer.current);
      }
    },
    [],
  );
  const handleDrillPass = (token: string) => {
    onWordDrillPass(token);
    const clearedNow = new Set([...clearedWords, token]);
    const after = practiceWords.findIndex(
      (word, index) => index > focusIndex && !clearedNow.has(word.token),
    );
    const fallback = practiceWords.findIndex(
      (word) => !clearedNow.has(word.token),
    );
    const target = after !== -1 ? after : fallback;
    if (target !== -1 && target !== focusIndex) {
      advanceTimer.current = window.setTimeout(() => {
        setFocusIndex(target);
      }, 1500);
    }
  };

  const sceneChip = (
    <span className="sfc-scene-chip">
      <BiLabel
        zh={`部分 ${selectedImageIndex + 1}/${totalScenes}`}
        en={`Scene ${selectedImageIndex + 1} of ${totalScenes}`}
      />
      {attempts > 0 && (
        <span className="sfc-attempt-chip">
          <BiLabel zh={`第 ${attempts} 次`} en={`Attempt ${attempts}`} />
        </span>
      )}
    </span>
  );

  const verdictContent = {
    meaning: {
      icon: "🧭",
      className: "sfc-verdict-meaning",
      text: (
        <BiLabel
          zh="先修正句子的意思，再管發音。"
          pinyin="Xiān xiūzhèng jùzi de yìsi, zài guǎn fāyīn."
          en="Fix what your sentence means first — pronunciation comes after."
        />
      ),
    },
    vocab: {
      icon: "📝",
      className: "sfc-verdict-vocab",
      text: (
        <BiLabel
          zh={`還缺 ${missing.length} 個詞：${missing.slice(0, 3).join("、")}`}
          pinyin={`Hái quē ${missing.length} ge cí: ${missing.slice(0, 3).join("、")}`}
          en={`${missing.length} word${missing.length > 1 ? "s" : ""} still missing: ${missing.slice(0, 3).join("、")}`}
        />
      ),
    },
    pronounce: {
      icon: "🎯",
      className: "sfc-verdict-pronounce",
      text: weakItems[0] ? (
        <BiLabel
          zh={`生詞都用到了！現在練「${weakItems[0].token}」的聲調。`}
          pinyin={`Shēngcí dōu yòng dào le! Xiànzài liàn “${weakItems[0].token}” de shēngdiào.`}
          en={`All words used! Now practice the tone of "${weakItems[0].token}".`}
        />
      ) : (
        <BiLabel
          zh="再錄一次，讓聲調更清楚。"
          pinyin="Zài lù yí cì, ràng shēngdiào gèng qīngchu."
          en="Record again and make your tones clearer."
        />
      ),
    },
    ready: {
      icon: "🎉",
      className: "sfc-verdict-ready",
      text: (
        <BiLabel
          zh={`部分 ${selectedImageIndex + 1} 完成！可以前往下一個部分。`}
          pinyin={`Bùfen ${selectedImageIndex + 1} wánchéng! Kěyǐ qiánwǎng xià yí ge bùfen.`}
          en={`Scene ${selectedImageIndex + 1} complete! You can move on.`}
        />
      ),
    },
  }[verdict];

  // Per-word tally for the overview stats line — only words the backend
  // actually judged (passed is a boolean) count either way.
  const judgedWords = (praatMetrics.word_prosody ?? []).filter(
    (word) => typeof word.passed === "boolean",
  );
  const passedCount = judgedWords.filter((word) => word.passed).length;

  // ── Step body: overview ───────────────────────────────────────────────
  const overviewStep = (
    <div className="sfc-step-panel">
      <header className={`sfc-verdict ${verdictContent.className}`}>
        <span className="sfc-verdict-icon" aria-hidden="true">
          {verdictContent.icon}
        </span>
        <div className="sfc-verdict-body">
          <p className="sfc-verdict-text">{verdictContent.text}</p>
        </div>
        {sceneChip}
      </header>

      {(analysisAudioBlob || praatMetrics.transcription || submittedAudioName) && (
        <div className="sfc-results-scene-extras">
          {analysisAudioBlob && <RecordingPlayback blob={analysisAudioBlob} />}
          {praatMetrics.transcription && (
            <p className="sfc-transcript">
              <BiLabel k="you_said" />{" "}
              <em lang="zh-TW">{praatMetrics.transcription}</em>
            </p>
          )}
          {submittedAudioName && (
            <p className="submitted-audio-name">✓ {submittedAudioName}</p>
          )}
        </div>
      )}

      {(judgedWords.length > 0 || vocabTotal > 0) && (
        <p className="sfc-stats-line">
          {judgedWords.length > 0 && (
            <span>
              🎯{" "}
              <BiLabel
                zh={`${passedCount}/${judgedWords.length} 個字 ✓`}
                en={`${passedCount}/${judgedWords.length} words ✓`}
              />
            </span>
          )}
          {vocabTotal > 0 && (
            <span>
              📝{" "}
              <BiLabel
                zh={`生詞 ${usedCount}/${vocabTotal}`}
                en={`Vocabulary ${usedCount}/${vocabTotal}`}
              />
            </span>
          )}
        </p>
      )}

      {hasPractice && (
        <div className="sfc-fail-preview">
          <span className="sfc-fail-preview-lead">
            <BiLabel zh="要練的字：" en="Words to practice:" />
          </span>
          {practiceWords.map((word, index) => {
            const cleared = clearedWords.includes(word.token);
            return (
              <button
                key={`${word.token}-${word.index}`}
                type="button"
                className={`sfc-mastery-chip sfc-fail-preview-chip ${cleared ? "is-cleared" : "is-pending"}`}
                onClick={() => {
                  setFocusIndex(index);
                  goToStep("practice");
                }}
              >
                {word.token} {cleared ? "✓" : "✗"}
              </button>
            );
          })}
        </div>
      )}

      {pronunciationNote?.details && pronunciationNote.details.length > 0 && (
        <div className="sfc-overview-details">
          <p className="block-label sfc-scene-detail-heading">
            <BiLabel zh="發音回饋" pinyin="Fāyīn huíkuì" en="Pronunciation Feedback" />
          </p>
          <div className="sfc-scene-detail-list">
            {pronunciationNote.details.map((d) => {
              const meta = PRONUNCIATION_DETAIL_LABELS[d.key];
              if (!meta) return null;
              return (
                <div key={d.key} className="sfc-scene-detail-item">
                  <p className="sfc-scene-detail-label">
                    <span aria-hidden="true">{meta.icon}</span>{" "}
                    <BiLabel zh={meta.zh} pinyin={meta.pinyin} en={meta.en} />
                  </p>
                  <p className="sfc-scene-detail-text">{d.text}</p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Forward CTA — where the verdict points, one obvious next action. */}
      {verdict === "meaning" && hasFix && (
        <button
          type="button"
          className="sfc-btn-next sfc-step-cta"
          onClick={() => goToStep("fix")}
        >
          <BiLabel zh="看怎麼改" en="See how to fix it" /> →
        </button>
      )}
      {verdict === "vocab" && hasFix && (
        <button
          type="button"
          className="sfc-btn-next sfc-step-cta"
          onClick={() => goToStep("fix")}
        >
          <BiLabel zh="看少了的生詞" en="See the missing words" /> →
        </button>
      )}
      {verdict === "pronounce" &&
        (hasPractice ? (
          <button
            type="button"
            className="sfc-btn-next sfc-step-cta"
            onClick={() => goToStep("practice")}
          >
            <BiLabel zh="練習生詞" en="Practice the words" /> →
          </button>
        ) : (
          <button
            type="button"
            className="sfc-btn-next sfc-step-cta"
            onClick={onRecordAgain}
          >
            🎙️ <BiLabel zh="再錄一次" en="Record again" />
          </button>
        ))}
    </div>
  );

  // ── Step body: fix (meaning + vocabulary) ─────────────────────────────
  const fixStep = (
    <div className="sfc-step-panel">
      {!accepted && (meaningJudged || showCorrective) && (
        <section className="sfc-result-card sfc-result-card--meaning is-bad">
          <header className="sfc-result-card-header">
            <span aria-hidden="true">🧭</span>
            <BiLabel zh="意思" en="Meaning" />
          </header>

          {meaningJudged && contentAccuracy?.feedback && (
            <div className="sfc-result-card-body">
              <p className="content-accuracy-feedback">
                {contentAccuracy.feedback}
              </p>
              {contentAccuracy.missed_details.length > 0 && (
                <p className="content-accuracy-missed">
                  ✗ {contentAccuracy.missed_details.join(", ")}
                </p>
              )}
            </div>
          )}

          {showCorrective && (
            <div
              className={`sfc-result-card-body sfc-corrective${corrective!.reveal_answer ? "" : " is-hint"}`}
            >
              <p className="sfc-corrective-heading">
                {corrective!.reveal_answer ? (
                  <BiLabel zh="正確答案" en="Correct version" />
                ) : (
                  <BiLabel zh="提示" en="Hint" />
                )}
              </p>
              {corrective!.hint && <p>{corrective!.hint}</p>}
              {corrective!.reveal_answer && corrective!.correct_version && (
                <p>
                  <strong>{corrective!.correct_version}</strong>
                </p>
              )}
            </div>
          )}
        </section>
      )}

      {missing.length > 0 && (
        <section className="sfc-result-card sfc-result-card--vocab">
          <header className="sfc-result-card-header">
            <span aria-hidden="true">📝</span>
            <BiLabel zh="生詞" en="Vocabulary" />
          </header>
          <div className="sfc-result-card-body">
            <p className="sfc-result-card-lead">
              <BiLabel zh="試著加入" en="Try to include" />
            </p>
            <div className="sfc-missing-chips">
              {missing.map((w) => (
                <span key={w} className="vocab-chip sfc-missing-chip">
                  {w}
                </span>
              ))}
            </div>
            {accepted && showCorrective && (
              <div
                className={`sfc-corrective${corrective!.reveal_answer ? "" : " is-hint"}`}
              >
                <p className="sfc-corrective-heading">
                  {corrective!.reveal_answer ? (
                    <BiLabel zh="正確答案" en="Correct version" />
                  ) : (
                    <BiLabel zh="提示" en="Hint" />
                  )}
                </p>
                {corrective!.hint && <p>{corrective!.hint}</p>}
                {corrective!.reveal_answer && corrective!.correct_version && (
                  <p>
                    <strong>{corrective!.correct_version}</strong>
                  </p>
                )}
              </div>
            )}
          </div>
        </section>
      )}

      <div className="sfc-step-cta-row">
        <button
          type="button"
          className="sfc-btn-next sfc-step-cta"
          onClick={onRecordAgain}
        >
          🎙️ <BiLabel zh="再錄一次" en="Record again" />
        </button>
        {hasPractice && (
          <button
            type="button"
            className="sfc-btn-again"
            onClick={() => goToStep("practice")}
          >
            <BiLabel zh="練習生詞" en="Practice the words" /> →
          </button>
        )}
      </div>
    </div>
  );

  // ── Step body: practice (one word at a time) ──────────────────────────
  const practiceStep = (
    <div className="sfc-step-panel">
      {allDrillsCleared ? (
        <div className="sfc-mastery-banner is-cleared">
          <p className="sfc-mastery-lead">
            🎉{" "}
            <BiLabel
              zh="這些字都好了！現在再錄一次整句。"
              pinyin="Zhèxiē zì dōu hǎo le! Xiànzài zài lù yí cì zhěng jù."
              en="All words cleared! Now record the whole sentence again."
            />
          </p>
        </div>
      ) : (
        <p className="sfc-mastery-lead sfc-practice-lead">
          🔑{" "}
          <BiLabel
            zh="先練好這些字，再錄整句："
            pinyin="Xiān liàn hǎo zhèxiē zì, zài lù zhěng jù:"
            en="First practice these words, then re-record the sentence:"
          />
        </p>
      )}

      <div className="sfc-practice-chips">
        {practiceWords.map((word, index) => {
          const cleared = clearedWords.includes(word.token);
          return (
            <button
              key={`${word.token}-${word.index}`}
              type="button"
              className={`sfc-mastery-chip sfc-practice-chip ${cleared ? "is-cleared" : "is-pending"}${index === focusIndex ? " is-current" : ""}`}
              onClick={() => setFocusIndex(index)}
              aria-pressed={index === focusIndex}
            >
              <span className="sfc-practice-chip-word">
                {word.token} {cleared ? "✓" : "✗"}
              </span>
              <span className="sfc-practice-chip-pinyin">
                {toPinyin(word.token)}
              </span>
            </button>
          );
        })}
      </div>

      {focusWord && (
        <>
          <div
            className="sfc-pronounce-legend mini-contour-legend"
            aria-hidden="true"
          >
            <span className="mini-contour-legend-actual">
              <BiLabel zh="你的音高" en="Your pitch" />
            </span>
            <span className="mini-contour-legend-reference">
              <BiLabel zh="目標形狀" en="Target shape" />
            </span>
          </div>
          <div className="sfc-focus-word">
            <WordProsodyCard
              key={`${focusWord.token}-${focusWord.index}`}
              item={focusWord}
              onDrillPass={handleDrillPass}
              drillDefaultOpen
            />
          </div>
        </>
      )}

      {allDrillsCleared && (
        <button
          type="button"
          className="sfc-btn-next sfc-step-cta"
          onClick={onRecordAgain}
        >
          🎙️ <BiLabel zh="再錄整句" en="Record the whole sentence" />
        </button>
      )}
    </div>
  );

  const stepBody = { overview: overviewStep, fix: fixStep, practice: practiceStep }[
    step
  ];

  return (
    <section
      className="speaking-flow-card sfc-results sfc-screen"
      aria-label="Recording results"
    >
      <div className="practice-workspace">
        {/* The scene image persists from the record screen at the same
            width/ratio — the anchor that makes record → results read as one
            continuous place. */}
        <div className="practice-scene-col">
          <div className="practice-scene-image">
            <img src={selectedImage} alt={`Scene ${selectedImageIndex + 1}`} />
          </div>
        </div>

        <div className="sfc-results-main">
          {steps.length > 1 && (
            <nav className="sfc-stepper" aria-label="Feedback steps">
              {steps.map((s, index) => {
                const current = s === step;
                const visited = index <= maxVisited;
                return (
                  <button
                    key={s}
                    type="button"
                    className={`sfc-step${current ? " is-current" : ""}${visited && !current ? " is-visited" : ""}`}
                    disabled={!visited}
                    aria-current={current ? "step" : undefined}
                    onClick={() => setStep(s)}
                  >
                    <span className="sfc-step-num">{index + 1}</span>
                    <BiLabel zh={STEP_LABELS[s].zh} en={STEP_LABELS[s].en} />
                  </button>
                );
              })}
            </nav>
          )}
          {stepBody}
        </div>
      </div>

      <footer className="sfc-footer">
        {!ready && !masteryPassed && practiceWords.length > 0 ? (
          <p className="sfc-unlock-note">
            🔒{" "}
            <BiLabel
              zh={`每個字都要 ✓ 才能過關 — 還有 ${remainingDrillWords.length > 0 ? `${remainingDrillWords.length} 個字要練` : "整句要再錄一次"}`}
              pinyin={`Měi ge zì dōu yào ✓ cáinéng guòguān — hái yǒu ${remainingDrillWords.length > 0 ? `${remainingDrillWords.length} ge zì yào liàn` : "zhěng jù yào zài lù yí cì"}`}
              en={`Every word needs a ✓ to pass — ${remainingDrillWords.length > 0 ? `${remainingDrillWords.length} word${remainingDrillWords.length > 1 ? "s" : ""} left to practice` : "re-record the whole sentence"}`}
            />
          </p>
        ) : !ready ? (
          <p className="sfc-unlock-note">
            🔒{" "}
            <BiLabel
              zh={`聲調 70 分、流暢 65 分，或練習 4 次即可打開（目前 ${attempts} 次）`}
              pinyin={`Shēngdiào 70 fēn, liúchàng 65 fēn, huò liànxí 4 cì jí kě dǎkāi (mùqián ${attempts} cì)`}
              en={`Unlock with tone 70, fluency 65, or 4 attempts (now: ${attempts})`}
            />
          </p>
        ) : null}
        <div className="sfc-footer-actions">
          <button type="button" className="sfc-btn-again" onClick={onRecordAgain}>
            🎙️ <BiLabel zh="再錄一次" pinyin="Zài lù yí cì" en="Record again" />
          </button>
          {hasNextScene ? (
            <button
              type="button"
              className="sfc-btn-next"
              disabled={!ready}
              onClick={onNextScene}
            >
              <BiLabel k="next_scene" /> →
            </button>
          ) : (
            <button
              type="button"
              className="sfc-btn-next"
              disabled={!ready}
              onClick={onViewSummary}
            >
              <BiLabel zh="查看總結" pinyin="Chákàn zǒngjié" en="View summary" /> →
            </button>
          )}
        </div>
      </footer>
    </section>
  );
}
