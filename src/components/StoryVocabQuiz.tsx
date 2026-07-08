import { useEffect, useMemo, useRef, useState } from "react";
import { BiLabel } from "./BiLabel";
import "./StoryVocabQuiz.css";

export interface VocabQuizEntry {
  word: string;
  translation: string;
}

export interface VocabQuizQuestion {
  word: string;
  correctTranslation: string;
  options: string[];
}

export interface VocabQuizQuestionResult {
  word: string;
  correct: boolean;
  timeMs: number;
}

export interface VocabQuizSummary {
  totalQuestions: number;
  correctCount: number;
  totalTimeMs: number;
  questionResults: VocabQuizQuestionResult[];
}

export type VocabQuizMode = "speed" | "strikes" | "free";

const MAX_QUESTIONS = 8;
const OPTION_COUNT = 4;

// Speed mode: forces quick, decisive answers (a per-question countdown) and
// caps the whole run (an overall countdown) — two distinct "speed" and
// "time" limits, not the same constraint twice.
const QUESTION_TIME_LIMIT_MS = 8_000;
const TOTAL_TIME_LIMIT_MS = 60_000;
const TIMER_TICK_MS = 100;

// Strikes mode: three wrong answers *in a row* ends the run early, like a
// game-over — a correct answer in between resets the counter.
const STRIKES_LIMIT = 3;

// Generic filler distractors, used only to pad out a question's wrong
// answers when the story itself doesn't have enough other translated words
// to draw real distractors from (common for a story with just 1-2 glossed
// words so far). Never shown as the correct answer.
const FILLER_DISTRACTORS = [
  "friend", "house", "water", "book", "school",
  "happy", "morning", "money", "food", "family",
  "teacher", "street", "weather", "car", "phone",
];

function shuffle<T>(items: T[]): T[] {
  const result = [...items];
  for (let i = result.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [result[i], result[j]] = [result[j], result[i]];
  }
  return result;
}

/** Dedupes a story's vocabulary (by word, across every scene) down to the
 * entries that have a translation filled in — a question can't be asked
 * about a word the teacher hasn't glossed. When `suggestedAnswers` is given
 * (one entry per word, aligned by index — typically the scene's suggested-
 * answer sentence repeated for each of that scene's words), a word is only
 * kept if it also actually appears in its scene's sentence, confirming it's
 * used in real context rather than an isolated flashcard pair. Without
 * `suggestedAnswers`, every translated word qualifies (no context to check
 * against). */
export function collectQuizEntries(
  words: string[],
  translations: Array<string | undefined>,
  suggestedAnswers?: Array<string | undefined>,
): VocabQuizEntry[] {
  const seen = new Set<string>();
  const entries: VocabQuizEntry[] = [];
  words.forEach((word, i) => {
    const translation = translations[i]?.trim();
    if (!translation || seen.has(word)) return;
    const context = suggestedAnswers?.[i];
    if (context !== undefined && !context.includes(word)) return;
    seen.add(word);
    entries.push({ word, translation });
  });
  return entries;
}

/** Builds up to MAX_QUESTIONS multiple-choice questions, one per entry, each
 * offering the correct translation plus up to OPTION_COUNT-1 distractors.
 * Distractors come from the story's own other translated words first; if
 * there aren't enough of those yet (e.g. only 1-2 words glossed so far),
 * generic filler words pad out the remaining options so a question is still
 * a real multiple-choice question, not a 1-option giveaway. */
export function buildQuizQuestions(entries: VocabQuizEntry[]): VocabQuizQuestion[] {
  const pool = shuffle(entries).slice(0, MAX_QUESTIONS);
  return pool.map((entry) => {
    const usedTranslations = new Set([entry.translation]);
    const realDistractorPool = entries
      .filter((e) => e.word !== entry.word && !usedTranslations.has(e.translation))
      .map((e) => e.translation);
    const realDistractors = shuffle(realDistractorPool).slice(0, OPTION_COUNT - 1);
    realDistractors.forEach((d) => usedTranslations.add(d));

    const fillerPool = FILLER_DISTRACTORS.filter((word) => !usedTranslations.has(word));
    const fillerDistractors = shuffle(fillerPool).slice(
      0,
      OPTION_COUNT - 1 - realDistractors.length,
    );

    const options = shuffle([entry.translation, ...realDistractors, ...fillerDistractors]);
    return { word: entry.word, correctTranslation: entry.translation, options };
  });
}

const MODES: Array<{ mode: VocabQuizMode; icon: string; title: string; titleEn: string; desc: string; descEn: string }> = [
  {
    mode: "speed",
    icon: "⏱️",
    title: "限時模式",
    titleEn: "Speed",
    desc: "每題 8 秒，全部限時 60 秒 — 越快越好。",
    descEn: "8s per question, 60s total — think fast.",
  },
  {
    mode: "strikes",
    icon: "❌",
    title: "三振模式",
    titleEn: "3 Strikes",
    desc: "連續答錯 3 題就結束 — 保持連對。",
    descEn: "3 wrong answers in a row ends the run.",
  },
  {
    mode: "free",
    icon: "🎯",
    title: "自由練習",
    titleEn: "Free Practice",
    desc: "沒有時間限制，慢慢來。",
    descEn: "No time limit, no elimination — go at your own pace.",
  },
];

/** A multiple-choice vocabulary check covering every glossed word in the
 * story, shown before a student starts practicing any scene. Mandatory
 * (no skip button) the first time through a story — once `onDone` fires
 * from actually finishing it, the caller is expected to remember that and
 * pass `allowSkip` on future visits. `onComplete`, when given, fires once
 * with a full results summary — only on a genuine finish of the *original*
 * round (every question answered, timed out, or eliminated by strikes),
 * never on skip/back-out, and never again for the missed-words retry round
 * offered afterward (that round is a same-session drill, not a new scored
 * attempt). */
export default function StoryVocabQuiz({
  entries,
  onDone,
  onBack,
  allowSkip = true,
  onComplete,
}: {
  entries: VocabQuizEntry[];
  onDone: () => void;
  onBack?: () => void;
  allowSkip?: boolean;
  onComplete?: (summary: VocabQuizSummary) => void;
}) {
  const [screen, setScreen] = useState<"mode-select" | "quiz" | "summary">("mode-select");
  const [mode, setMode] = useState<VocabQuizMode | null>(null);
  const [roundEntries, setRoundEntries] = useState(entries);
  const [isRetryRound, setIsRetryRound] = useState(false);

  const questions = useMemo(() => buildQuizQuestions(roundEntries), [roundEntries]);
  const [index, setIndex] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [results, setResults] = useState<VocabQuizQuestionResult[]>([]);
  const [consecutiveFails, setConsecutiveFails] = useState(0);
  const [questionTimeLeftMs, setQuestionTimeLeftMs] = useState(QUESTION_TIME_LIMIT_MS);
  const questionStartRef = useRef(Date.now());
  const quizStartRef = useRef(Date.now());

  const question = questions[index];
  const isLast = index === questions.length - 1;
  const isTimedOut = selected === "__timeout__";

  // Guards against finishing twice: the speed-mode ticker can fire several
  // times before React re-renders and tears the interval down (e.g. several
  // ticks land past the total-time cap in the same batch), and without this
  // guard each of those would re-report onComplete and re-enter "summary".
  const finishedRef = useRef(false);

  const finish = (finalResults: VocabQuizQuestionResult[]) => {
    if (finishedRef.current) return;
    finishedRef.current = true;
    if (!isRetryRound) {
      onComplete?.({
        totalQuestions: finalResults.length,
        correctCount: finalResults.filter((r) => r.correct).length,
        totalTimeMs: Date.now() - quizStartRef.current,
        questionResults: finalResults,
      });
    }
    setScreen("summary");
  };

  const recordAnswer = (correct: boolean, chosen: string) => {
    setSelected(chosen);
    const nextResults = [
      ...results,
      { word: question.word, correct, timeMs: Date.now() - questionStartRef.current },
    ];
    setResults(nextResults);

    if (mode === "strikes") {
      const nextFails = correct ? 0 : consecutiveFails + 1;
      setConsecutiveFails(nextFails);
      if (nextFails >= STRIKES_LIMIT) {
        // Let the student see the final (losing) answer highlighted for a
        // beat before ending the run, same rhythm as a normal answer.
        window.setTimeout(() => finish(nextResults), 700);
        return;
      }
    }
  };

  const choose = (option: string) => {
    if (selected) return;
    recordAnswer(option === question.correctTranslation, option);
  };

  const next = () => {
    setSelected(null);
    setQuestionTimeLeftMs(QUESTION_TIME_LIMIT_MS);
    if (isLast) {
      finish(results);
    } else {
      questionStartRef.current = Date.now();
      setIndex((i) => i + 1);
    }
  };

  // Speed mode: one ticking clock drives both the per-question countdown
  // (forces a quick answer) and the overall run cap (checked each tick
  // against wall-clock elapsed time, so it survives tab throttling better
  // than decrementing a separate counter).
  useEffect(() => {
    if (mode !== "speed" || screen !== "quiz" || selected) return;
    const tick = window.setInterval(() => {
      if (Date.now() - quizStartRef.current >= TOTAL_TIME_LIMIT_MS) {
        finish(results);
        return;
      }
      setQuestionTimeLeftMs((t) => Math.max(0, t - TIMER_TICK_MS));
    }, TIMER_TICK_MS);
    return () => window.clearInterval(tick);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, screen, selected, index]);

  useEffect(() => {
    if (mode !== "speed" || screen !== "quiz" || selected) return;
    if (questionTimeLeftMs <= 0) {
      recordAnswer(false, "__timeout__");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [questionTimeLeftMs, mode, screen, selected]);

  const chooseMode = (picked: VocabQuizMode) => {
    setMode(picked);
    setScreen("quiz");
    setIndex(0);
    setSelected(null);
    setResults([]);
    setConsecutiveFails(0);
    setQuestionTimeLeftMs(QUESTION_TIME_LIMIT_MS);
    quizStartRef.current = Date.now();
    questionStartRef.current = Date.now();
    finishedRef.current = false;
  };

  const missedWords = results.filter((r) => !r.correct);
  const missedEntries = roundEntries.filter((e) =>
    missedWords.some((r) => r.word === e.word),
  );

  const practiceMissedWords = () => {
    setIsRetryRound(true);
    setRoundEntries(missedEntries);
    chooseMode("free");
  };

  if (screen === "mode-select") {
    return (
      <section className="story-vocab-quiz vocab-quiz-mode-select" aria-label="Vocabulary quiz">
        {onBack && (
          <button type="button" className="btn-vocab-quiz-back" onClick={onBack}>
            <BiLabel zh="← 返回活動" en="← Back to activities" />
          </button>
        )}
        <div className="vocab-quiz-header">
          <p className="eyebrow">
            <BiLabel zh="詞彙測驗" en="Vocabulary Quiz" />
          </p>
          <h1 className="vocab-quiz-mode-title">
            <BiLabel zh="選一種模式" en="Pick a mode" />
          </h1>
        </div>
        <div className="vocab-quiz-mode-grid" role="group" aria-label="Quiz mode">
          {MODES.map((m) => (
            <button
              key={m.mode}
              type="button"
              className={`vocab-quiz-mode-card vocab-quiz-mode-${m.mode}`}
              onClick={() => chooseMode(m.mode)}
            >
              <span className="vocab-quiz-mode-icon">{m.icon}</span>
              <strong>
                <BiLabel zh={m.title} en={m.titleEn} />
              </strong>
              <p>
                <BiLabel zh={m.desc} en={m.descEn} />
              </p>
            </button>
          ))}
        </div>
        {allowSkip && (
          <button type="button" className="btn-skip-vocab-quiz" onClick={onDone}>
            <BiLabel k="skip" />
          </button>
        )}
      </section>
    );
  }

  if (screen === "summary") {
    const correctCount = results.filter((r) => r.correct).length;
    return (
      <section className="story-vocab-quiz vocab-quiz-summary" aria-label="Vocabulary quiz results">
        <div className="vocab-quiz-header">
          <p className="eyebrow">
            <BiLabel
              zh={isRetryRound ? "複習結果" : "測驗結果"}
              en={isRetryRound ? "Review results" : "Quiz results"}
            />
          </p>
          <h1 className="vocab-quiz-mode-title">
            <BiLabel
              zh={`答對 ${correctCount} / ${results.length} 題`}
              en={`${correctCount} / ${results.length} correct`}
            />
          </h1>
        </div>

        {missedWords.length > 0 ? (
          <div className="vocab-quiz-missed-list" role="list" aria-label="Missed words">
            {missedEntries.map((entry) => (
              <div className="vocab-quiz-missed-item" role="listitem" key={entry.word}>
                <span className="vocab-quiz-missed-word">{entry.word}</span>
                <span className="vocab-quiz-missed-translation">{entry.translation}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="vocab-quiz-all-correct">
            <BiLabel zh="全部答對，太棒了！" en="Perfect score — nice work!" />
          </p>
        )}

        <div className="vocab-quiz-actions">
          {missedWords.length > 0 && !isRetryRound && (
            <button type="button" className="btn-vocab-quiz-retry" onClick={practiceMissedWords}>
              <BiLabel zh="🔁 練習答錯的題目" en="🔁 Practice missed words" />
            </button>
          )}
          <button type="button" className="btn-vocab-quiz-next" onClick={onDone}>
            <BiLabel zh="繼續練習 →" en="Continue to practice →" />
          </button>
        </div>
      </section>
    );
  }

  if (!question) {
    return null;
  }

  return (
    <section className="story-vocab-quiz" aria-label="Vocabulary quiz">
      {onBack && (
        <button type="button" className="btn-vocab-quiz-back" onClick={onBack}>
          <BiLabel zh="← 返回活動" en="← Back to activities" />
        </button>
      )}
      <div className="vocab-quiz-header">
        <p className="eyebrow">
          <BiLabel
            zh={isRetryRound ? "複習答錯的題目" : "詞彙測驗"}
            en={isRetryRound ? "Reviewing missed words" : "Vocabulary Quiz"}
          />
        </p>
        <h1 className="vocab-quiz-word">{question.word}</h1>
        <p className="vocab-quiz-progress">
          <BiLabel
            zh={`第 ${index + 1} / ${questions.length} 題`}
            en={`Question ${index + 1} of ${questions.length}`}
          />
        </p>
        {mode === "speed" && (
          <p
            className={`vocab-quiz-timer${questionTimeLeftMs <= 3000 ? " urgent" : ""}`}
            aria-label={`${Math.ceil(questionTimeLeftMs / 1000)} seconds left`}
          >
            ⏱️ {Math.ceil(questionTimeLeftMs / 1000)}s
          </p>
        )}
        {mode === "strikes" && (
          <p className="vocab-quiz-strikes" aria-label={`${consecutiveFails} of ${STRIKES_LIMIT} strikes`}>
            {Array.from({ length: STRIKES_LIMIT }, (_, i) => (
              <span key={i} className={i < consecutiveFails ? "strike-used" : "strike-open"}>
                {i < consecutiveFails ? "❌" : "◯"}
              </span>
            ))}
          </p>
        )}
      </div>

      <div
        className="vocab-quiz-options"
        role="group"
        aria-label={`What does ${question.word} mean?`}
      >
        {question.options.map((option) => {
          const isCorrect = option === question.correctTranslation;
          const isChosen = option === selected;
          const state = selected
            ? isCorrect
              ? "correct"
              : isChosen
                ? "incorrect"
                : "neutral"
            : "neutral";
          return (
            <button
              key={option}
              type="button"
              className={`vocab-quiz-option vocab-quiz-option-${state}`}
              onClick={() => choose(option)}
              disabled={Boolean(selected)}
            >
              {option}
            </button>
          );
        })}
      </div>

      {isTimedOut && (
        <p className="vocab-quiz-timeout-note">
          <BiLabel zh="時間到！" en="Time's up!" />
        </p>
      )}

      <div className="vocab-quiz-actions">
        {selected &&
          !(mode === "strikes" && consecutiveFails >= STRIKES_LIMIT) && (
            <button type="button" className="btn-vocab-quiz-next" onClick={next}>
              {isLast ? (
                <BiLabel zh="開始練習" en="Start practice" />
              ) : (
                <BiLabel zh="下一題" en="Next question" />
              )}
            </button>
          )}
        {allowSkip && !isRetryRound && (
          <button type="button" className="btn-skip-vocab-quiz" onClick={onDone}>
            <BiLabel k="skip" />
          </button>
        )}
      </div>
    </section>
  );
}
