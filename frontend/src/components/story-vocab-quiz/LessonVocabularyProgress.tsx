import { BiLabel } from "../BiLabel";
import StudentIcon from "../StudentIcon";
import type { LessonRoundProgress, LessonVocabularyProgress } from "./lesson-vocab-progress";
import { nextLearningStage } from "./lesson-vocab-progress";

type ProgressStage = "review" | "knowIt" | "sayIt" | "useIt" | "strengthen" | "challenge";

const STAGES: Array<{ key: ProgressStage; zh: string; pinyin: string; en: string }> = [
  { key: "review", zh: "生詞複習", pinyin: "Shēngcí fùxí", en: "Vocabulary Review" },
  { key: "knowIt", zh: "認識它", pinyin: "Rènshi tā", en: "Know It" },
  { key: "sayIt", zh: "說出來", pinyin: "Shuō chūlái", en: "Say It" },
  { key: "useIt", zh: "用起來", pinyin: "Yòng qǐlái", en: "Use It" },
  { key: "strengthen", zh: "加強詞彙", pinyin: "Jiāqiáng cíhuì", en: "Strengthen" },
  { key: "challenge", zh: "課程挑戰", pinyin: "Kèchéng tiǎozhàn", en: "Lesson Challenge" },
];

function roundSummary(round: LessonRoundProgress) {
  if (!round.completed) return "Not started";
  return `${round.correct} / ${round.total}`;
}

function stageState(progress: LessonVocabularyProgress, key: ProgressStage): "complete" | "current" | "available" {
  if (key === "review") return progress.vocabularyReviewCompleted ? "complete" : "current";
  if (key === "knowIt") return progress.knowIt.completed ? "complete" : "current";
  if (key === "sayIt") return progress.sayIt.completed ? "complete" : progress.knowIt.completed ? "current" : "available";
  if (key === "useIt") return progress.useIt.completed ? "complete" : progress.sayIt.completed ? "current" : "available";
  if (key === "strengthen") return progress.strengthen.completed ? "complete" : progress.useIt.completed ? "current" : "available";
  return progress.challenge.attempts > 0 ? "complete" : progress.challenge.available ? "available" : "available";
}

function stageDetail(progress: LessonVocabularyProgress, key: ProgressStage): string | null {
  if (key === "knowIt") return roundSummary(progress.knowIt);
  if (key === "sayIt") return roundSummary(progress.sayIt);
  if (key === "useIt") return roundSummary(progress.useIt);
  if (key === "strengthen") return progress.strengthen.remaining > 0 ? `${progress.strengthen.remaining} remaining` : `${progress.strengthen.strengthened} strengthened`;
  if (key === "challenge" && progress.challenge.bestScore !== undefined) return `Best ${progress.challenge.bestScore} / ${progress.totalWords}`;
  return null;
}

export function MasteryProgressBar({ progress, compact = false }: { progress: LessonVocabularyProgress; compact?: boolean }) {
  const percent = progress.totalWords > 0 ? Math.round((progress.strongWords / progress.totalWords) * 100) : 0;
  return (
    <section className={`lesson-vocab-mastery${compact ? " is-compact" : ""}`} aria-label="Lesson vocabulary mastery">
      <div className="lesson-vocab-mastery-heading">
        <div>
          <strong>{progress.strongWords} / {progress.totalWords}</strong>
        </div>
      </div>
      <div className="lesson-vocab-mastery-track" role="progressbar" aria-label={`${progress.strongWords} of ${progress.totalWords} vocabulary words strong`} aria-valuemin={0} aria-valuemax={progress.totalWords} aria-valuenow={progress.strongWords}>
        <span style={{ width: `${percent}%` }} />
      </div>
    </section>
  );
}

export function StrengthenProgressBar({ progress }: { progress: LessonVocabularyProgress }) {
  const total = progress.strengthen.required;
  const strengthened = Math.min(total, progress.strengthen.strengthened);
  const percent = total > 0 ? Math.round((strengthened / total) * 100) : 100;
  return (
    <section className="lesson-vocab-mastery lesson-strengthen-progress" aria-label="Strengthen vocabulary progress">
      <div className="lesson-vocab-mastery-heading">
        <div>
          <strong>{strengthened} / {total}</strong>
        </div>
      </div>
      <div className="lesson-vocab-mastery-track" role="progressbar" aria-label={`${strengthened} of ${total} vocabulary words strengthened`} aria-valuemin={0} aria-valuemax={total} aria-valuenow={strengthened}>
        <span style={{ width: `${percent}%` }} />
      </div>
    </section>
  );
}

export function LessonLearningPath({ progress }: { progress: LessonVocabularyProgress }) {
  return (
    <section className="lesson-learning-path" aria-label="Lesson learning path">
      <div className="lesson-learning-path-heading">
        <div>
          <p className="eyebrow"><BiLabel zh="學習路徑" pinyin="Xuéxí lùjìng" en="Learning path" /></p>
          <h2><BiLabel zh="一步一步完成本課" pinyin="Yí bù yí bù wánchéng běn kè" en="Your lesson path" /></h2>
        </div>
        {progress.lessonCompleted && <span className="lesson-learning-path-complete"><StudentIcon name="check-circle" size={16} /> Complete</span>}
      </div>
      <ol className="lesson-learning-path-list">
        {STAGES.map((stage) => {
          const state = stageState(progress, stage.key);
          const detail = stageDetail(progress, stage.key);
          return (
            <li key={stage.key} className={`lesson-learning-path-step is-${state}`}>
              <span className="lesson-learning-path-marker" aria-hidden="true">{state === "complete" ? "✓" : state === "current" ? "●" : "○"}</span>
              <div>
                <strong><BiLabel zh={stage.zh} pinyin={stage.pinyin} en={stage.en} /></strong>
                {detail && <span>{detail}</span>}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

export function RoundStats({ progress }: { progress: LessonVocabularyProgress }) {
  const rounds: Array<{ label: string; round: LessonRoundProgress }> = [
    { label: "Know It", round: progress.knowIt },
    { label: "Say It", round: progress.sayIt },
    { label: "Use It", round: progress.useIt },
  ];
  return (
    <section className="lesson-round-stats" aria-label="Lesson round statistics">
      {rounds.map(({ label, round }) => (
        <div className="lesson-round-stat" key={label}>
          <span>{label}</span>
          <strong>{round.completed ? `${round.correct} / ${round.total}` : "—"}</strong>
          <small>{round.completed ? `${round.accuracy}% accuracy` : "Not started"}</small>
        </div>
      ))}
    </section>
  );
}

export function LessonProgressOverview({ progress, onContinue }: { progress: LessonVocabularyProgress; onContinue?: () => void }) {
  const nextStage = nextLearningStage(progress);
  const nextCopy: Record<Exclude<typeof nextStage, "complete">, string> = {
    knowIt: "Start Know It",
    sayIt: "Continue to Say It",
    useIt: "Continue to Use It",
    strengthen: `Strengthen ${progress.strengthen.remaining} Words`,
  };
  return (
    <section className="lesson-progress-overview" aria-label="Lesson progress overview">
      <MasteryProgressBar progress={progress} />
      <LessonLearningPath progress={progress} />
      {onContinue && nextStage !== "complete" && <button type="button" className="lesson-progress-continue" onClick={onContinue}>{nextCopy[nextStage]}</button>}
    </section>
  );
}

export function FocusWords({ progress, onStart }: { progress: LessonVocabularyProgress; onStart?: () => void }) {
  if (progress.focusWords.length === 0 && progress.remainingWords === 0) return null;
  return (
    <section className="lesson-focus-words" aria-label="Words to strengthen">
      <div className="lesson-focus-words-heading">
        <div>
          <p className="eyebrow"><BiLabel zh="需要加強" pinyin="Xūyào jiāqiáng" en="Needs more practice" /></p>
          <h2><BiLabel zh="要加強的詞" pinyin="Yào jiāqiáng de cí" en="Words to Strengthen" /></h2>
        </div>
        {onStart && progress.remainingWords > 0 && <button type="button" className="lesson-focus-words-action" onClick={onStart}>Strengthen {progress.remainingWords} words</button>}
      </div>
      {progress.focusWords.length > 0 ? (
        <ul>{progress.focusWords.slice(0, 8).map((word) => <li key={word.wordId}><strong>{word.word}</strong>{word.meaning && <span>{word.meaning}</span>}</li>)}</ul>
      ) : <p className="lesson-focus-words-empty"><BiLabel zh="完成三個 round 後，系統會在這裡顯示需要加強的詞。" pinyin="Wánchéng sān gè round hòu, xìtǒng huì zài zhèlǐ xiǎnshì xūyào jiāqiáng de cí." en="Complete the three rounds to see words that need more practice here." /></p>}
    </section>
  );
}

export function ChallengeEntry({ progress, onStart, onBack }: { progress: LessonVocabularyProgress; onStart: () => void; onBack?: () => void }) {
  return (
    <section className="story-vocab-quiz vocab-quiz-challenge-entry-screen" aria-label="Lesson challenge">
      {onBack && <button type="button" className="btn-vocab-quiz-back" onClick={onBack}><StudentIcon name="arrow-left" size={17} /><BiLabel zh="選模式" pinyin="Xuǎn móshì" en="Back to modes" /></button>}
      <section className="lesson-challenge-entry" aria-label="Challenge details">
      <div>
        <p className="eyebrow"><BiLabel zh="額外練習" pinyin="Éwài liànxí" en="Optional extra practice" /></p>
        <h2><StudentIcon name="star" size={18} /> <BiLabel zh="課程挑戰" pinyin="Kèchéng tiǎozhàn" en="Lesson Challenge" /></h2>
        <p><BiLabel zh={`混合 ${progress.totalWords} 個詞的題型。`} pinyin={`Hùnhé ${progress.totalWords} gè cí de tíxíng.`} en={`Mixed question types across all ${progress.totalWords} lesson words.`} /></p>
        <small>{progress.challenge.bestScore === undefined ? "Best score: —" : `Best score: ${progress.challenge.bestScore} / ${progress.totalWords}`}</small>
      </div>
      <button type="button" className="lesson-challenge-start" disabled={!progress.challenge.available} onClick={onStart}>{progress.challenge.available ? "Start Challenge" : "Available after the three rounds"}</button>
      </section>
    </section>
  );
}

export function LessonCompletionSummary({ progress, onFinish }: { progress: LessonVocabularyProgress; onFinish?: () => void }) {
  if (!progress.lessonCompleted) return null;
  return (
    <section className="lesson-completion-summary" aria-label="Lesson vocabulary complete">
      <div className="lesson-completion-heading">
        <div>
          <p className="eyebrow"><BiLabel zh="本課完成" pinyin="Běn kè wánchéng" en="Lesson complete" /></p>
          <h2><StudentIcon name="check-circle" size={20} /> <BiLabel zh="本課詞彙完成！" pinyin="Běn kè cíhuì wánchéng!" en="Lesson Vocabulary Complete" /></h2>
        </div>
        {onFinish && <button type="button" className="lesson-completion-finish" onClick={onFinish}>Finish</button>}
      </div>
      <div className="lesson-completion-stats">
        <span><strong>{progress.totalWords}</strong> words practised</span>
        <span><strong>{progress.initialStrongCount}</strong> strong on first check</span>
        <span><strong>{progress.strengthenedCount}</strong> strengthened through practice</span>
      </div>
      <MasteryProgressBar progress={progress} compact />
      {progress.improvements.filter((item) => item.strengthenedThroughPractice).length > 0 && (
        <div className="lesson-improved-today">
          <strong>Improved today</strong>
          <ul>{progress.improvements.filter((item) => item.strengthenedThroughPractice).map((item) => <li key={item.wordId}><span>{item.targetWord}</span><span>Needs Practice → Strong ✓</span></li>)}</ul>
        </div>
      )}
    </section>
  );
}
