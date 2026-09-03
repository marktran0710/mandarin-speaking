import { BiLabel } from "../BiLabel";
import StudentIcon from "../StudentIcon";
import { toPinyin } from "../../utils/pinyin";
import { TIER_CARDS, REVIEW_CARD, type VocabAssessmentLevel, type VocabQuizEntry, type VocabQuizMode, type VocabQuizQuestionResult } from "./model";
import type { VocabPriorityReviewWord } from "../../services/database";
import { TIER_CONFIGS, attemptEarnsStar, effectiveTierPassCount, isTierUnlocked, nextStarGap, practiceUnlocked, tierConfigFromMode, type QuizTier, type TierMode } from "../../utils/quizTiers";

const LEVEL_COPY: Record<"easy" | "medium" | "hard", { zh: string; pinyin: string; en: string }> = {
  easy: { zh: "簡單", pinyin: "Jiǎndān", en: "Easy" },
  medium: { zh: "中等", pinyin: "Zhōngděng", en: "Medium" },
  hard: { zh: "困難", pinyin: "Kùnnán", en: "Hard" },
};

interface WeakWordsCardProps {
  weakEntries: VocabQuizEntry[];
  priorityReviewWords: VocabPriorityReviewWord[];
  chooseWeakWords: () => void;
}

function WeakWordsCard({ weakEntries, priorityReviewWords, chooseWeakWords }: WeakWordsCardProps) {
  const aggregateWeakCount = priorityReviewWords.length || weakEntries.length;
  const priorityList = priorityReviewWords.length > 0 && (
    <ul className="vocab-quiz-priority-list">
      {priorityReviewWords.map((word) => (
        <li key={word.wordId}>
          <span className="vocab-quiz-priority-word">{word.word}</span>
          <span>{word.meaning || "Vocabulary review"}</span>
          <span>{word.status.replace("_", " ").toLowerCase()} · {word.observationCount} observations</span>
        </li>
      ))}
    </ul>
  );

  if (aggregateWeakCount === 0) {
    return (
      <section
        className="vocab-quiz-mode-card vocab-quiz-mode-weak_words is-empty"
        aria-label="Weak words"
      >
        <span className="vocab-quiz-mode-icon">
          <StudentIcon name="retry" size={30} />
        </span>
        <strong><BiLabel zh="弱項複習" pinyin="Ruòxiàng fùxí" en="Weak words" /></strong>
        <p>
          <BiLabel
            zh="目前還沒有需要加強的生詞。"
            pinyin="Mùqián hái méiyǒu xūyào jiāqiáng de shēngcí."
            en="No weak words yet. Complete a quiz to build your review list."
          />
        </p>
      </section>
    );
  }

  // The endpoint is intentionally story-wide, while this quiz instance may
  // be rendering only one difficulty tier. Keep the cumulative BKT list
  // visible even when its words belong to another tier; there is no local
  // question set to start from in that case.
  if (weakEntries.length === 0) {
    return (
      <section className="vocab-quiz-mode-card vocab-quiz-mode-weak_words is-summary-only" aria-label="Weak words">
        <span className="vocab-quiz-mode-icon"><StudentIcon name="retry" size={30} /></span>
        <strong><BiLabel zh={`弱項複習 (${aggregateWeakCount})`} pinyin="Ruòxiàng fùxí" en={`Weak words (${aggregateWeakCount})`} /></strong>
        <p><BiLabel zh="這些弱項來自本故事的其他難度，切換到對應難度即可練習。" pinyin="Zhèxiē ruòxiàng láizì běn gùshì de qítā nándù, qiēhuàn dào duìyìng nándù jí kě liànxí." en="These weak words are from another difficulty level. Open that level to practice them." /></p>
        {priorityList}
      </section>
    );
  }

  return (
    <button type="button" className="vocab-quiz-mode-card vocab-quiz-mode-weak_words" onClick={chooseWeakWords}>
      <span className="vocab-quiz-mode-icon"><StudentIcon name="retry" size={30} /></span>
      <strong><BiLabel zh={`弱項複習 (${aggregateWeakCount})`} pinyin="Ruòxiàng fùxí" en={`Weak words (${aggregateWeakCount})`} /></strong>
      <p><BiLabel zh="這是本故事各個難度累積的弱項，會從掌握度最低的詞開始。" pinyin="Zhè shì běn gùshì gè gè nándù lěijī de ruòxiàng, huì cóng zhǎngwòdù zuì dī de cí kāishǐ." en="A cumulative list across this story's difficulty levels, starting with the words you know least." /></p>
      {priorityList}
      <StudentIcon name="arrow-right" size={18} />
    </button>
  );
}

export function ModeSelectScreen({ stars, weakEntries, priorityReviewWords = [], level = "easy", assessmentQuestionCounts, startTier, chooseWeakWords, showReview }: { stars: 0 | QuizTier; weakEntries: VocabQuizEntry[]; priorityReviewWords?: VocabPriorityReviewWord[]; level?: "easy" | "medium" | "hard"; assessmentQuestionCounts?: Partial<Record<VocabAssessmentLevel, number>>; startTier: (mode: TierMode) => void; chooseWeakWords: () => void; showReview: () => void }) {
  const assessmentLevelByMode: Record<TierMode, VocabAssessmentLevel> = { tier1: "easy", tier2: "medium", tier3: "hard" };
  const tierDescription = (card: (typeof TIER_CARDS)[number], config: (typeof TIER_CONFIGS)[TierMode]) => {
    const count = assessmentQuestionCounts?.[assessmentLevelByMode[card.mode]];
    if (!count) return { zh: card.desc, pinyin: card.descPinyin, en: card.descEn };
    const passCount = effectiveTierPassCount(config, count);
    const timeSuffix = config.timeLimitMs ? `，${config.timeLimitMs / 1000} 秒` : "";
    return {
      zh: `${count} 題${timeSuffix} — 答對 ${passCount} 題就過關。`,
      pinyin: `${count} tí${timeSuffix ? `, ${config.timeLimitMs! / 1000} miǎo` : ""} — dá duì ${passCount} tí jiù guòguān.`,
      en: `${count} question${count === 1 ? "" : "s"}${config.timeLimitMs ? ` in ${config.timeLimitMs / 1000}s` : ""} — ${passCount} right to pass.`,
    };
  };
  return <section className="story-vocab-quiz vocab-quiz-mode-select" aria-label="Vocabulary quiz">
    <div className="vocab-quiz-header"><div className="vocab-quiz-header-tags"><p className="eyebrow"><BiLabel zh="生詞測驗" pinyin="Shēngcí cèyàn" en="Vocabulary Quiz" /></p><p className="vocab-quiz-level-badge"><BiLabel zh={LEVEL_COPY[level].zh} pinyin={LEVEL_COPY[level].pinyin} en={LEVEL_COPY[level].en} /></p></div><h1 className="vocab-quiz-mode-title">{practiceUnlocked(stars)
      ? <BiLabel zh="三顆星都拿到了！" pinyin="Sān kē xīng dōu nádào le!" en="All three stars earned" />
      : <BiLabel zh="拿到三顆星，開始說話練習" pinyin="Nádào sān kē xīng, kāishǐ shuōhuà liànxí" en="Earn three stars to open speaking practice" />}</h1><p className="vocab-quiz-star-count" aria-label={`${stars} of 3 stars earned`}>{([1, 2, 3] as const).map((tier) => <span key={tier} className={stars >= tier ? "star-earned" : "star-open"}><StudentIcon name="star" size={26} fill={stars >= tier ? "currentColor" : "none"} /></span>)}</p></div>
    <div className="vocab-quiz-mode-grid" role="group" aria-label="Quiz mode">{TIER_CARDS.map((card) => { const config = TIER_CONFIGS[card.mode]; const unlocked = isTierUnlocked(config.tier, stars); const earned = stars >= config.tier; const description = tierDescription(card, config); return <button key={card.mode} type="button" className={`vocab-quiz-mode-card vocab-quiz-mode-${card.mode}${unlocked ? "" : " is-locked"}${earned ? " is-earned" : ""}`} disabled={!unlocked} onClick={() => startTier(card.mode)}><span className="vocab-quiz-mode-icon"><StudentIcon name={unlocked ? card.iconName : "lock"} size={30} /></span><strong><BiLabel zh={card.title} pinyin={card.titlePinyin} en={card.titleEn} />{earned && <StudentIcon name="check-circle" size={15} aria-label="Star earned" />}</strong><p>{unlocked ? <BiLabel zh={description.zh} pinyin={description.pinyin} en={description.en} /> : <BiLabel zh={`先拿到 ${config.tier - 1} 顆星。`} pinyin={`Xiān nádào ${config.tier - 1} kē xīng.`} en={`Earn ${config.tier - 1} star${config.tier - 1 === 1 ? "" : "s"} first.`} />}</p></button>; })}
      <div className="vocab-quiz-secondary-grid">
        <button type="button" className="vocab-quiz-mode-card vocab-quiz-mode-review" onClick={showReview}><span className="vocab-quiz-mode-icon"><StudentIcon name={REVIEW_CARD.iconName} size={30} /></span><strong><BiLabel zh={REVIEW_CARD.title} pinyin={REVIEW_CARD.titlePinyin} en={REVIEW_CARD.titleEn} /></strong><p><BiLabel zh={REVIEW_CARD.desc} pinyin={REVIEW_CARD.descPinyin} en={REVIEW_CARD.descEn} /></p><StudentIcon name="arrow-right" size={18} /></button>
        <WeakWordsCard
          weakEntries={weakEntries}
          priorityReviewWords={priorityReviewWords}
          chooseWeakWords={chooseWeakWords}
        />
      </div>
    </div>
  </section>;
}

export function ReviewScreen({ entries, back }: { entries: VocabQuizEntry[]; back: () => void }) {
  return <section className="story-vocab-quiz vocab-quiz-review" aria-label="Vocabulary review"><button type="button" className="btn-vocab-quiz-back" onClick={back}><StudentIcon name="arrow-left" size={17} /><BiLabel zh="選模式" pinyin="Xuǎn móshì" en="Back to modes" /></button><div className="vocab-quiz-header"><p className="eyebrow"><BiLabel zh="複習模式" pinyin="Fùxí móshì" en="Review Mode" /></p><h1 className="vocab-quiz-mode-title"><BiLabel zh="所有生詞" pinyin="Suǒyǒu shēngcí" en="All vocabulary" /></h1></div><ul className="vocab-quiz-review-list" aria-label="Vocabulary list">{entries.map((entry) => <li className="vocab-quiz-review-item" key={entry.word}><span className="vocab-quiz-review-word">{entry.word}</span><span className="vocab-quiz-review-pinyin">{entry.pinyin || toPinyin(entry.word)}</span><span className="vocab-quiz-review-translation">{entry.translation}</span></li>)}</ul></section>;
}

export function SummaryScreen({ mode, results, missedWords, missedEntries, isRetryRound, stars, onDone, startTier, practiceMissedWords, backToModes }: { mode: VocabQuizMode | null; results: VocabQuizQuestionResult[]; missedWords: VocabQuizQuestionResult[]; missedEntries: VocabQuizEntry[]; isRetryRound: boolean; stars: 0 | QuizTier; onDone: () => void; startTier: (mode: TierMode) => void; practiceMissedWords: () => void; backToModes: () => void }) {
  const correctCount = results.filter((result) => result.correct).length;
  const tierConfig = !isRetryRound ? tierConfigFromMode(mode) : null;
  const passed = attemptEarnsStar(mode, correctCount, results.length) !== null;
  const gap = tierConfig ? nextStarGap(mode, correctCount, results.length)! : null;
  const nextTierCard = tierConfig && passed && tierConfig.tier < 3 ? TIER_CARDS.find((card) => TIER_CONFIGS[card.mode].tier === tierConfig.tier + 1)! : null;
  const showContinue = practiceUnlocked(stars);
  return <section className="story-vocab-quiz vocab-quiz-summary" aria-label="Vocabulary quiz results"><div className="vocab-quiz-header"><p className="eyebrow"><BiLabel zh={isRetryRound ? "複習結果" : "測驗結果"} pinyin={isRetryRound ? "Fùxí jiéguǒ" : "Cèyàn jiéguǒ"} en={isRetryRound ? "Review results" : "Quiz results"} /></p><h1 className="vocab-quiz-mode-title"><BiLabel zh={`答對 ${correctCount} / ${results.length} 題`} pinyin={`Dá duì ${correctCount} / ${results.length} tí`} en={`${correctCount} / ${results.length} correct`} /></h1>{tierConfig && passed && <p className="vocab-quiz-star-result is-earned"><BiLabel zh={`你拿到第 ${tierConfig.tier} 顆星了！`} pinyin={`Nǐ nádào dì ${tierConfig.tier} kē xīng le!`} en={`You earned star ${tierConfig.tier}!`} /></p>}{tierConfig && !passed && <p className="vocab-quiz-star-result is-near-miss"><BiLabel zh={`再答對 ${gap} 題就拿到第 ${tierConfig.tier} 顆星了！`} pinyin={`Zài dá duì ${gap} tí jiù nádào dì ${tierConfig.tier} kē xīng le!`} en={`Just ${gap} more right for star ${tierConfig.tier}!`} /></p>}</div>
    {missedWords.length > 0 ? <div className="vocab-quiz-missed-list" role="list" aria-label="Missed words">{missedEntries.map((entry) => <div className="vocab-quiz-missed-item" role="listitem" key={entry.word}><span className="vocab-quiz-missed-word">{entry.word}</span><span className="vocab-quiz-missed-translation">{entry.translation}</span></div>)}</div> : <p className="vocab-quiz-all-correct"><BiLabel zh="全部答對，太棒了！" pinyin="Quánbù dá duì, tài bàng le!" en="Perfect score — nice work!" /></p>}
    <div className="vocab-quiz-actions">{tierConfig && !passed && <button type="button" className="btn-vocab-quiz-try-again" onClick={() => startTier(tierConfig.mode)}><StudentIcon name="retry" size={16} /> <BiLabel zh="再試一次" pinyin="Zài shì yí cì" en="Try again" /></button>}{nextTierCard && <button type="button" className="btn-vocab-quiz-challenge" onClick={() => startTier(nextTierCard.mode)}><StudentIcon name="star" size={16} /> <BiLabel zh={`挑戰${nextTierCard.title}`} pinyin={`Tiǎozhàn ${nextTierCard.titlePinyin.toLowerCase()}`} en={`Challenge ${nextTierCard.titleEn}`} /></button>}{missedWords.length > 0 && !isRetryRound && <button type="button" className="btn-vocab-quiz-retry" onClick={practiceMissedWords}><StudentIcon name="retry" size={16} /> <BiLabel zh="練習答錯的題目" pinyin="Liànxí dá cuò de tímù" en="Practice missed words" /></button>}{showContinue ? <button type="button" className="btn-vocab-quiz-next" onClick={onDone}><BiLabel zh="繼續練習" pinyin="Jìxù liànxí" en="Continue to practice" /> <StudentIcon name="arrow-right" size={16} aria-hidden="true" /></button> : <button type="button" className="btn-vocab-quiz-menu" onClick={backToModes}><BiLabel zh="回選單" pinyin="Huí xuǎndān" en="Back to menu" /></button>}</div>
    {!showContinue && <p className="vocab-quiz-unlock-note"><StudentIcon name="lock" size={15} /> <BiLabel zh="拿到三顆星才能開始說話練習" pinyin="Nádào sān kē xīng cáinéng kāishǐ shuōhuà liànxí" en="Speaking practice opens after all three stars" /></p>}
  </section>;
}
