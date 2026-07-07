import { useMemo, useState } from "react";
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

const MAX_QUESTIONS = 8;
const OPTION_COUNT = 4;

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
 * about a word the teacher hasn't glossed. */
export function collectQuizEntries(
  words: string[],
  translations: Array<string | undefined>,
): VocabQuizEntry[] {
  const seen = new Set<string>();
  const entries: VocabQuizEntry[] = [];
  words.forEach((word, i) => {
    const translation = translations[i]?.trim();
    if (!translation || seen.has(word)) return;
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

/** A multiple-choice vocabulary check covering every glossed word in the
 * story, shown before a student starts practicing any scene. Mandatory
 * (no skip button) the first time through a story — once `onDone` fires
 * from actually finishing it, the caller is expected to remember that and
 * pass `allowSkip` on future visits. */
export default function StoryVocabQuiz({
  entries,
  onDone,
  onBack,
  allowSkip = true,
}: {
  entries: VocabQuizEntry[];
  onDone: () => void;
  onBack?: () => void;
  allowSkip?: boolean;
}) {
  const questions = useMemo(() => buildQuizQuestions(entries), [entries]);
  const [index, setIndex] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);

  const question = questions[index];

  if (!question) {
    return null;
  }

  const isLast = index === questions.length - 1;

  const choose = (option: string) => {
    if (selected) return;
    setSelected(option);
  };

  const next = () => {
    setSelected(null);
    if (isLast) {
      onDone();
    } else {
      setIndex((i) => i + 1);
    }
  };

  return (
    <section className="story-vocab-quiz" aria-label="Vocabulary quiz">
      {onBack && (
        <button type="button" className="btn-vocab-quiz-back" onClick={onBack}>
          <BiLabel zh="← 返回活動" en="← Back to activities" />
        </button>
      )}
      <div className="vocab-quiz-header">
        <p className="eyebrow">
          <BiLabel zh="詞彙測驗" en="Vocabulary Quiz" />
        </p>
        <h1 className="vocab-quiz-word">{question.word}</h1>
        <p className="vocab-quiz-progress">
          <BiLabel
            zh={`第 ${index + 1} / ${questions.length} 題`}
            en={`Question ${index + 1} of ${questions.length}`}
          />
        </p>
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

      <div className="vocab-quiz-actions">
        {selected && (
          <button type="button" className="btn-vocab-quiz-next" onClick={next}>
            {isLast ? (
              <BiLabel zh="開始練習" en="Start practice" />
            ) : (
              <BiLabel zh="下一題" en="Next question" />
            )}
          </button>
        )}
        {allowSkip && (
          <button type="button" className="btn-skip-vocab-quiz" onClick={onDone}>
            <BiLabel k="skip" />
          </button>
        )}
      </div>
    </section>
  );
}
