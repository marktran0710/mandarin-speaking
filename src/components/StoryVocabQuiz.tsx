import { useEffect, useRef, useState } from "react";
import { BiLabel } from "./BiLabel";
import { toPinyin } from "../utils/pinyin";
import "./StoryVocabQuiz.css";

export interface VocabQuizEntry {
  word: string;
  translation: string;
  // Teacher-authored pinyin for this word, if any — falls back to a computed
  // reading (see the Review screen) when absent.
  pinyin?: string;
  // AI-generated wrong-but-plausible translations for this word (see
  // buildQuestionForEntry) — undefined/empty falls back to the old
  // real-word-pool + generic-filler distractor logic.
  aiDistractors?: string[];
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
  mode: VocabQuizMode;
  totalQuestions: number;
  correctCount: number;
  totalTimeMs: number;
  questionResults: VocabQuizQuestionResult[];
}

export type VocabQuizMode = "speed" | "strikes" | "free";

const MAX_QUESTIONS = 8;
const OPTION_COUNT = 4;

// Speed mode: a fixed 20-question run capped at 60 seconds total — no
// per-question timer, just an overall countdown, so the pressure is "get
// through as many as you can before time's up" rather than a forced answer
// on every single question.
const SPEED_QUESTION_COUNT = 20;
const TOTAL_TIME_LIMIT_MS = 60_000;
const TIMER_TICK_MS = 100;

// Strikes mode: three wrong answers *in a row* ends the run early, like a
// game-over — a correct answer in between resets the counter. Free and
// Strikes both draw from an unlimited, endlessly-reshuffled pool of the
// story's words (see drawFromBag below) rather than a fixed question count
// — they end only via their own condition (strikes) or the student's own
// choice (the "Finish" button), never by running out of questions.
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
  aiDistractors?: Array<string[] | undefined>,
  pinyins?: Array<string | undefined>,
): VocabQuizEntry[] {
  const seen = new Set<string>();
  const entries: VocabQuizEntry[] = [];
  words.forEach((word, i) => {
    const translation = translations[i]?.trim();
    if (!translation || seen.has(word)) return;
    const context = suggestedAnswers?.[i];
    if (context !== undefined && !context.includes(word)) return;
    seen.add(word);
    const distractors = aiDistractors?.[i];
    const pinyin = pinyins?.[i]?.trim();
    entries.push({
      word,
      translation,
      ...(distractors?.length ? { aiDistractors: distractors } : {}),
      ...(pinyin ? { pinyin } : {}),
    });
  });
  return entries;
}

/** Builds one multiple-choice question for `entry`, offering its correct
 * translation plus up to OPTION_COUNT-1 distractors. AI-generated distractors
 * (near-synonyms, same part of speech — real wrong answers a student might
 * actually pick) are used first when available; the story's other translated
 * words, then generic filler words, pad out any remaining slots — covering
 * both a story with no AI distractors yet and one where the AI returned
 * fewer than OPTION_COUNT-1 for a word. */
function buildQuestionForEntry(
  entry: VocabQuizEntry,
  allEntries: VocabQuizEntry[],
): VocabQuizQuestion {
  const usedTranslations = new Set([entry.translation]);

  const aiPool = (entry.aiDistractors ?? []).filter((d) => !usedTranslations.has(d));
  const aiDistractors = shuffle(aiPool).slice(0, OPTION_COUNT - 1);
  aiDistractors.forEach((d) => usedTranslations.add(d));

  const realDistractorPool = Array.from(
    new Set(
      allEntries
        .filter((e) => e.word !== entry.word && !usedTranslations.has(e.translation))
        .map((e) => e.translation),
    ),
  );
  const realDistractors = shuffle(realDistractorPool).slice(
    0,
    OPTION_COUNT - 1 - aiDistractors.length,
  );
  realDistractors.forEach((d) => usedTranslations.add(d));

  const fillerPool = FILLER_DISTRACTORS.filter((word) => !usedTranslations.has(word));
  const fillerDistractors = shuffle(fillerPool).slice(
    0,
    OPTION_COUNT - 1 - aiDistractors.length - realDistractors.length,
  );

  const options = shuffle([
    entry.translation,
    ...aiDistractors,
    ...realDistractors,
    ...fillerDistractors,
  ]);
  return { word: entry.word, correctTranslation: entry.translation, options };
}

/** Builds up to MAX_QUESTIONS multiple-choice questions, one per entry, all
 * at once. The live quiz below generates questions one at a time instead
 * (an endless shuffle-bag, so Speed/Strikes/Free/retry rounds can each set
 * their own question count independently) — this batch form is kept as a
 * standalone utility. */
export function buildQuizQuestions(entries: VocabQuizEntry[]): VocabQuizQuestion[] {
  const pool = shuffle(entries).slice(0, MAX_QUESTIONS);
  return pool.map((entry) => buildQuestionForEntry(entry, entries));
}

const MODES: Array<{
  mode: VocabQuizMode | "review";
  icon: string;
  title: string;
  titlePinyin: string;
  titleEn: string;
  desc: string;
  descPinyin: string;
  descEn: string;
}> = [
  {
    mode: "speed",
    icon: "⏱️",
    title: "快速模式",
    titlePinyin: "Kuàisù móshì",
    titleEn: "Speed",
    desc: "20 題，總共 60 秒 — 越快越好。",
    descPinyin: "20 tí, zǒnggòng 60 miǎo — yuè kuài yuè hǎo.",
    descEn: "20 questions, 60s total — think fast.",
  },
  {
    mode: "strikes",
    icon: "❌",
    title: "三次機會",
    titlePinyin: "Sān cì jīhuì",
    titleEn: "3 Strikes",
    desc: "題目沒有限制，錯 3 題就結束 — 小心一點。",
    descPinyin: "Tímù méiyǒu xiànzhì, cuò 3 tí jiù jiéshù — xiǎoxīn yìdiǎn.",
    descEn: "Unlimited questions — 3 wrong answers in a row ends the run.",
  },
  {
    mode: "review",
    icon: "📖",
    title: "複習模式",
    titlePinyin: "Fùxí móshì",
    titleEn: "Review",
    desc: "沒有題目限制 — 直接看所有詞彙和它們的聲調。",
    descPinyin: "Méiyǒu tímù xiànzhì — zhíjiē kàn suǒyǒu cíhuì hàn tāmen de shēngdiào.",
    descEn: "No question limit — just browse every word and its tones.",
  },
];

/** A multiple-choice vocabulary check covering every glossed word in the
 * story, shown before a student starts practicing any scene. Always
 * mandatory — no skip button in any scored mode; `onBack` (if given) is the
 * only way out before finishing, and it doesn't count as completion.
 * Review mode is the exception: it's a browsable list, not a quiz, so it
 * never produces a summary and never unlocks practice on its own. `onComplete`,
 * when given, fires once with a full results summary — only on a genuine
 * finish of the *original* Speed/Strikes round (every question answered,
 * timed out, or eliminated by strikes), never on back-out, and never again
 * for the missed-words retry round offered afterward (that round is a
 * same-session drill, not a new scored attempt). */
export default function StoryVocabQuiz({
  entries,
  onDone,
  onBack,
  onComplete,
}: {
  entries: VocabQuizEntry[];
  onDone: () => void;
  onBack?: () => void;
  onComplete?: (summary: VocabQuizSummary) => void;
}) {
  const [screen, setScreen] = useState<"mode-select" | "quiz" | "review" | "summary">("mode-select");
  const [mode, setMode] = useState<VocabQuizMode | null>(null);
  const [roundEntries, setRoundEntries] = useState(entries);
  const [isRetryRound, setIsRetryRound] = useState(false);
  // null = unlimited (Strikes/Free): questions are generated endlessly from
  // a reshuffled bag until the mode's own condition or the student ends it.
  // A number bounds the round to exactly that many questions (Speed = 20,
  // a missed-words retry = exactly that many missed words).
  const [questionLimit, setQuestionLimit] = useState<number | null>(null);

  const [questions, setQuestions] = useState<VocabQuizQuestion[]>([]);
  const bagRef = useRef<VocabQuizEntry[]>([]);
  const [index, setIndex] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [results, setResults] = useState<VocabQuizQuestionResult[]>([]);
  const [consecutiveFails, setConsecutiveFails] = useState(0);
  const questionStartRef = useRef(Date.now());
  const quizStartRef = useRef(Date.now());

  const question = questions[index];
  const isLast = questionLimit !== null && index === questionLimit - 1;
  // "free" is no longer offered from mode-select (replaced by Review), but
  // its unlimited/no-timer engine still powers the missed-words retry below
  // — always with a real questionLimit there, so this stays false in
  // practice. Kept rather than deleted in case an unlimited scored mode is
  // ever wanted again.
  const showFinishButton = mode === "free" && questionLimit === null;

  // Draws the next entry from an endlessly-reshuffled "bag" — every entry is
  // asked once before any repeats, rather than pure random-with-replacement.
  const drawFromBag = (pool: VocabQuizEntry[]): VocabQuizEntry => {
    if (bagRef.current.length === 0) bagRef.current = shuffle(pool);
    return bagRef.current.shift()!;
  };

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
        mode: mode!,
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
    if (isLast) {
      finish(results);
      return;
    }
    questionStartRef.current = Date.now();
    const nextIndex = index + 1;
    if (!questions[nextIndex]) {
      const nextQuestion = buildQuestionForEntry(drawFromBag(roundEntries), roundEntries);
      setQuestions((qs) => [...qs, nextQuestion]);
    }
    setIndex(nextIndex);
  };

  // Speed mode: no per-question timer — just an overall 60s cap on the whole
  // run, checked each tick against wall-clock elapsed time (so it survives
  // tab throttling better than a decrementing counter).
  useEffect(() => {
    if (mode !== "speed" || screen !== "quiz" || selected) return;
    const tick = window.setInterval(() => {
      if (Date.now() - quizStartRef.current >= TOTAL_TIME_LIMIT_MS) {
        finish(results);
      }
    }, TIMER_TICK_MS);
    return () => window.clearInterval(tick);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, screen, selected, index]);

  // `entriesForRound`/`limit` are explicit params (not read from state) so
  // a retry launched via practiceMissedWords() below can't read a stale
  // `roundEntries` closure from before its own setRoundEntries takes effect.
  const chooseMode = (
    picked: VocabQuizMode,
    entriesForRound: VocabQuizEntry[],
    limit: number | null,
  ) => {
    setMode(picked);
    setScreen("quiz");
    setRoundEntries(entriesForRound);
    setQuestionLimit(limit);
    setIndex(0);
    setSelected(null);
    setResults([]);
    setConsecutiveFails(0);
    bagRef.current = shuffle(entriesForRound);
    setQuestions([buildQuestionForEntry(bagRef.current.shift()!, entriesForRound)]);
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
    chooseMode("free", missedEntries, missedEntries.length);
  };

  if (screen === "mode-select") {
    return (
      <section className="story-vocab-quiz vocab-quiz-mode-select" aria-label="Vocabulary quiz">
        {onBack && (
          <button type="button" className="btn-vocab-quiz-back" onClick={onBack}>
            <BiLabel zh="← 回活動" pinyin="← Huí huódòng" en="← Back to activities" />
          </button>
        )}
        <div className="vocab-quiz-header">
          <p className="eyebrow">
            <BiLabel zh="詞彙測驗" pinyin="Cíhuì cèyàn" en="Vocabulary Quiz" />
          </p>
          <h1 className="vocab-quiz-mode-title">
            <BiLabel zh="選一種模式" pinyin="Xuǎn yì zhǒng móshì" en="Pick a mode" />
          </h1>
        </div>
        <div className="vocab-quiz-mode-grid" role="group" aria-label="Quiz mode">
          {MODES.map((m) => (
            <button
              key={m.mode}
              type="button"
              className={`vocab-quiz-mode-card vocab-quiz-mode-${m.mode}`}
              onClick={() =>
                m.mode === "review"
                  ? setScreen("review")
                  : chooseMode(m.mode, entries, m.mode === "speed" ? SPEED_QUESTION_COUNT : null)
              }
            >
              <span className="vocab-quiz-mode-icon">{m.icon}</span>
              <strong>
                <BiLabel zh={m.title} pinyin={m.titlePinyin} en={m.titleEn} />
              </strong>
              <p>
                <BiLabel zh={m.desc} pinyin={m.descPinyin} en={m.descEn} />
              </p>
            </button>
          ))}
        </div>
      </section>
    );
  }

  if (screen === "review") {
    return (
      <section className="story-vocab-quiz vocab-quiz-review" aria-label="Vocabulary review">
        <button
          type="button"
          className="btn-vocab-quiz-back"
          onClick={() => setScreen("mode-select")}
        >
          <BiLabel zh="← 選模式" pinyin="← Xuǎn móshì" en="← Back to modes" />
        </button>
        <div className="vocab-quiz-header">
          <p className="eyebrow">
            <BiLabel zh="複習模式" pinyin="Fùxí móshì" en="Review Mode" />
          </p>
          <h1 className="vocab-quiz-mode-title">
            <BiLabel zh="所有詞彙" pinyin="Suǒyǒu cíhuì" en="All vocabulary" />
          </h1>
        </div>
        <ul className="vocab-quiz-review-list" aria-label="Vocabulary list">
          {entries.map((entry) => (
            <li className="vocab-quiz-review-item" key={entry.word}>
              <span className="vocab-quiz-review-word">{entry.word}</span>
              <span className="vocab-quiz-review-pinyin">
                {entry.pinyin || toPinyin(entry.word)}
              </span>
              <span className="vocab-quiz-review-translation">{entry.translation}</span>
            </li>
          ))}
        </ul>
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
              pinyin={isRetryRound ? "Fùxí jiéguǒ" : "Cèyàn jiéguǒ"}
              en={isRetryRound ? "Review results" : "Quiz results"}
            />
          </p>
          <h1 className="vocab-quiz-mode-title">
            <BiLabel
              zh={`答對 ${correctCount} / ${results.length} 題`}
              pinyin={`Dá duì ${correctCount} / ${results.length} tí`}
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
            <BiLabel zh="全部答對，太棒了！" pinyin="Quánbù dá duì, tài bàng le!" en="Perfect score — nice work!" />
          </p>
        )}

        <div className="vocab-quiz-actions">
          {missedWords.length > 0 && !isRetryRound && (
            <button type="button" className="btn-vocab-quiz-retry" onClick={practiceMissedWords}>
              <BiLabel zh="🔁 練習答錯的題目" pinyin="🔁 Liànxí dá cuò de tímù" en="🔁 Practice missed words" />
            </button>
          )}
          <button type="button" className="btn-vocab-quiz-next" onClick={onDone}>
            <BiLabel zh="繼續練習 →" pinyin="Jìxù liànxí →" en="Continue to practice →" />
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
      <div className="vocab-quiz-topbar">
        {onBack && (
          <button type="button" className="btn-vocab-quiz-back" onClick={onBack}>
            <BiLabel zh="← 回活動" pinyin="← Huí huódòng" en="← Back to activities" />
          </button>
        )}
        {showFinishButton && (
          <button type="button" className="btn-vocab-quiz-finish" onClick={() => finish(results)}>
            <BiLabel zh="結束，看結果" pinyin="Jiéshù, kàn jiéguǒ" en="Finish & see results" />
          </button>
        )}
      </div>
      <div className="vocab-quiz-header">
        <p className="eyebrow">
          <BiLabel
            zh={isRetryRound ? "複習答錯的題目" : "詞彙測驗"}
            pinyin={isRetryRound ? "Fùxí dá cuò de tímù" : "Cíhuì cèyàn"}
            en={isRetryRound ? "Reviewing missed words" : "Vocabulary Quiz"}
          />
        </p>
        <h1 className="vocab-quiz-word">{question.word}</h1>
        <p className="vocab-quiz-progress">
          {questionLimit !== null ? (
            <BiLabel
              zh={`第 ${index + 1} / ${questionLimit} 題`}
              pinyin={`Dì ${index + 1} / ${questionLimit} tí`}
              en={`Question ${index + 1} of ${questionLimit}`}
            />
          ) : (
            <BiLabel zh={`第 ${index + 1} 題`} pinyin={`Dì ${index + 1} tí`} en={`Question ${index + 1}`} />
          )}
        </p>
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
              aria-label={
                state === "correct"
                  ? `${option} (correct answer)`
                  : state === "incorrect"
                    ? `${option} (your answer, incorrect)`
                    : undefined
              }
            >
              {state === "correct" && (
                <span className="vocab-quiz-option-icon" aria-hidden="true">✓ </span>
              )}
              {state === "incorrect" && (
                <span className="vocab-quiz-option-icon" aria-hidden="true">✗ </span>
              )}
              {option}
            </button>
          );
        })}
      </div>

      <div className="vocab-quiz-actions">
        {selected &&
          !(mode === "strikes" && consecutiveFails >= STRIKES_LIMIT) && (
            <button type="button" className="btn-vocab-quiz-next" onClick={next}>
              {isLast ? (
                <BiLabel zh="開始練習" pinyin="Kāishǐ liànxí" en="Start practice" />
              ) : (
                <BiLabel zh="下一題" pinyin="Xià yì tí" en="Next question" />
              )}
            </button>
          )}
      </div>
    </section>
  );
}
