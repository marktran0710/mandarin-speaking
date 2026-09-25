import { useEffect, useState } from "react";
import type { Topic } from "../../components/content/topic-selector/types";
import {
  type VocabQuizEntry,
  type VocabQuizMode,
  type VocabQuizQuestion,
  type VocabQuizQuestionResult,
} from "@entities/vocabulary";
import type { TierMode } from "@entities/vocabulary";
import { toPinyin } from "../../utils/pinyin";
import { useVocabQuizFlow } from "./hooks/useVocabQuizFlow";
import { ROUND_LABEL, TIER_SEQUENCE } from "./model/tierRounds";
import BilingualWord from "@shared/ui/student/BilingualWord";
import StudentAudioControl from "@shared/ui/student/StudentAudioControl";
import StudentButton from "@shared/ui/student/StudentButton";
import StudentIcon from "@shared/ui/student/StudentIcon";
import StudentSection from "@shared/ui/student/StudentSection";
import StudentStatusPill from "@shared/ui/student/StudentStatusPill";
import "@shared/ui/student/layout.css";
import "./VocabularyQuizPage.css";

interface VocabularyQuizPageProps {
  topic: Topic;
  lessonLabel: string;
  onFinished: () => void;
}

const QUESTION_TYPE_LABELS: Record<string, string> = {
  basic_meaning_mcq: "Meaning check",
  character_to_pinyin_typing: "Reading recall",
  context_cloze_mcq: "Context clue",
  productive_recall: "Active recall",
  contextual_productive_recall: "Context recall",
};

const QUESTION_KIND_LABELS: Record<VocabQuizQuestion["kind"], string> = {
  translation: "Meaning check",
  cloze: "Context clue",
  pinyin: "Reading recall",
  pos: "Word class",
  synonym: "Related meaning",
  reverse: "Character recall",
  listening: "Listening check",
  assessment: "Assessment item",
};

const ROUND_DESCRIPTIONS: Record<TierMode, string> = {
  tier1: "Recognise the meaning of each lesson word.",
  tier2: "Recall the reading and form of each word.",
  tier3: "Use the words in context before speaking practice.",
};

function roundName(mode: VocabQuizMode | null, tierPos: number): string {
  if (mode && mode in ROUND_LABEL) return ROUND_LABEL[mode as TierMode];
  return ROUND_LABEL[TIER_SEQUENCE[tierPos]];
}

function questionTypeLabel(question: VocabQuizQuestion): string {
  if (question.kind === "assessment") {
    return QUESTION_TYPE_LABELS[question.assessment.questionType] ?? "Assessment item";
  }
  return QUESTION_KIND_LABELS[question.kind];
}

function promptFor(question: VocabQuizQuestion): string {
  switch (question.kind) {
    case "assessment": return question.prompt;
    case "cloze": return question.sentenceWithBlank;
    case "reverse": return `Choose the Chinese word for “${question.translation}”.`;
    case "pinyin": return "Choose the correct pinyin reading.";
    case "pos": return "Choose the word class that best describes this word.";
    case "synonym": return "Choose the closest related meaning.";
    case "listening": return "Listen to the model and choose the matching word.";
    case "translation": return "Choose the English meaning of this word.";
  }
}

function entryFor(entries: VocabQuizEntry[], question: VocabQuizQuestion | null): VocabQuizEntry | undefined {
  if (!question) return undefined;
  return entries.find((entry) => entry.word === question.word);
}

function resultAt(results: VocabQuizQuestionResult[], index: number): VocabQuizQuestionResult | undefined {
  return results.find((result) => result.questionIndex === index) ?? results[index];
}

function formatTime(milliseconds: number): string {
  const seconds = Math.max(0, Math.ceil(milliseconds / 1000));
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

function QuizHeader({
  flow,
  lessonLabel,
  question,
}: {
  flow: ReturnType<typeof useVocabQuizFlow>;
  lessonLabel: string;
  question: VocabQuizQuestion | null;
}) {
  const total = flow.questionLimit ?? flow.entries.length;
  const completed = flow.results.length;
  const progress = total > 0 ? Math.min(100, (completed / total) * 100) : 0;

  return (
    <div className="sa-quiz__header">
      <div className="sa-quiz__header-copy">
        <p className="sa-quiz__breadcrumb">Study <span aria-hidden="true">/</span> {lessonLabel}</p>
        <div className="sa-quiz__title-row">
          <h1 className="sa-quiz__title">
            <span lang="zh-Hant">詞彙練習</span>
            <span className="sa-quiz__title-en">Vocabulary Quiz</span>
          </h1>
          <span className="sa-quiz__round-tag">{roundName(flow.mode, flow.tierPos)}</span>
        </div>
      </div>

      <div className="sa-quiz__header-meta" aria-label="Quiz status">
        {question && (
          <span className="sa-quiz__meta-chip">
            <StudentIcon name="quiz" size={16} role="decorative" />
            Question {flow.index + 1} / {total}
          </span>
        )}
        {typeof flow.timeLimitMs === "number" && Number.isFinite(flow.timeLimitMs) && (
          <span className="sa-quiz__meta-chip">
            <StudentIcon name="timer" size={16} role="decorative" />
            {formatTime(flow.timeLeftMs)}
          </span>
        )}
      </div>

      <div
        className="sa-quiz__progress"
        role="progressbar"
        aria-label="Quiz progress"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={completed}
      >
        <span style={{ width: `${progress}%` }} />
      </div>
    </div>
  );
}

function ModePicker({ flow }: { flow: ReturnType<typeof useVocabQuizFlow> }) {
  const tier = TIER_SEQUENCE[flow.tierPos];
  const weakCount = flow.weakEntries.length || flow.interimReviewEntries.length;
  const dueCount = flow.dueWords.length;

  return (
    <div className="sa-quiz__mode-layout">
      <section className="sa-quiz__mode-main" aria-labelledby="quiz-mode-title">
        <div className="sa-quiz__mode-intro">
          <div>
            <StudentStatusPill tone="info" icon="route">Guided practice</StudentStatusPill>
            <h2 id="quiz-mode-title">Choose a practice path</h2>
            <p>Build a reliable word foundation, then return to the words that need more attention.</p>
          </div>
          <div className="sa-quiz__star-summary" aria-label={`${flow.stars} of 3 stars earned`}>
            <StudentIcon name="hotel_class" size={20} role="decorative" filled />
            <strong>{flow.stars}</strong><span>/ 3 stars</span>
          </div>
        </div>

        <div className="sa-quiz__mode-grid">
          <StudentSection variant="panel" className="sa-quiz__mode-card sa-quiz__mode-card--primary">
            <div className="sa-quiz__mode-index">01</div>
            <div className="sa-quiz__mode-copy">
              <p className="sa-quiz__mode-kicker">Diagnostic path</p>
              <h3>{ROUND_LABEL[tier]}</h3>
              <p>{ROUND_DESCRIPTIONS[tier]}</p>
              <div className="sa-quiz__mode-detail"><StudentIcon name="lock_open" size={15} role="decorative" /><span>Rounds unlock in order</span></div>
            </div>
            <StudentButton variant="primary" iconTrailing="arrow_forward" onClick={flow.startTier}>
              Start {ROUND_LABEL[tier]}
            </StudentButton>
          </StudentSection>

          <StudentSection variant="panel" className="sa-quiz__mode-card">
            <div className="sa-quiz__mode-index">02</div>
            <div className="sa-quiz__mode-copy">
              <p className="sa-quiz__mode-kicker">Personalised practice</p>
              <h3>Weak words</h3>
              <p>Practice from your current learning record.</p>
              <div className="sa-quiz__mode-detail"><StudentIcon name="psychology" size={15} role="decorative" /><span>{weakCount > 0 ? `${weakCount} words ready` : "No words queued yet"}</span></div>
            </div>
            <StudentButton variant="secondary" icon="fitness_center" disabled={weakCount === 0} onClick={flow.startWeakWords}>
              Practice weak words
            </StudentButton>
          </StudentSection>

          <StudentSection variant="panel" className="sa-quiz__mode-card">
            <div className="sa-quiz__mode-index">03</div>
            <div className="sa-quiz__mode-copy">
              <p className="sa-quiz__mode-kicker">Spaced review</p>
              <h3>Review today</h3>
              <p>Review words that are due in your learning schedule.</p>
              <div className="sa-quiz__mode-detail"><StudentIcon name="event_repeat" size={15} role="decorative" /><span>{dueCount > 0 ? `${dueCount} words due` : "Nothing due today"}</span></div>
            </div>
            <StudentButton variant="secondary" icon="schedule" disabled={dueCount === 0} onClick={flow.startDueReview}>
              Review due words
            </StudentButton>
          </StudentSection>
        </div>
      </section>

      <aside className="sa-quiz__mode-rail" aria-label="Practice overview">
        <StudentSection variant="panel" className="sa-quiz__rail-card">
          <div className="sa-quiz__rail-heading"><span>Practice overview</span><StudentStatusPill tone="success">Active session</StudentStatusPill></div>
          <dl className="sa-quiz__overview-list">
            <div><dt>Lesson words</dt><dd>{flow.entries.length}</dd></div>
            <div><dt>Stars earned</dt><dd>{flow.stars} / 3</dd></div>
            <div><dt>Speaking gate</dt><dd>{flow.stars >= 3 ? "Open" : "Locked"}</dd></div>
          </dl>
        </StudentSection>
        <StudentSection variant="tinted" className="sa-quiz__rail-card sa-quiz__round-guide">
          <div className="sa-quiz__rail-heading"><span>Diagnostic sequence</span><StudentIcon name="stairs" size={18} role="decorative" /></div>
          <ol>
            {TIER_SEQUENCE.map((round, index) => (
              <li key={round} className={index < flow.tierPos ? "is-complete" : index === flow.tierPos ? "is-current" : ""}>
                <span>{index + 1}</span><div><strong>{ROUND_LABEL[round]}</strong><small>{ROUND_DESCRIPTIONS[round]}</small></div>
              </li>
            ))}
          </ol>
        </StudentSection>
      </aside>
    </div>
  );
}

function QuizRail({
  flow,
  hint,
  hintOpen,
  onToggleHint,
}: {
  flow: ReturnType<typeof useVocabQuizFlow>;
  hint?: string;
  hintOpen: boolean;
  onToggleHint: () => void;
}) {
  const total = flow.questionLimit ?? flow.entries.length;
  const correct = flow.results.filter((result) => result.correct).length;
  const accuracy = flow.results.length > 0 ? `${Math.round((correct / flow.results.length) * 100)}%` : "—";

  return (
    <aside className="sa-quiz__rail" aria-label="Quiz progress and support">
      <StudentSection variant="panel" className="sa-quiz__rail-card">
        <div className="sa-quiz__rail-heading"><span>Assessment</span><StudentStatusPill tone="success">In progress</StudentStatusPill></div>
        <div className="sa-quiz__stats">
          <div><span>Accuracy</span><strong>{accuracy}</strong></div>
          <div><span>Done</span><strong>{flow.results.length}<small> / {total}</small></strong></div>
          <div><span>Left</span><strong>{Math.max(0, total - flow.results.length)}</strong></div>
        </div>
      </StudentSection>

      {hint && (
        <StudentSection variant="panel" className={`sa-quiz__rail-card sa-quiz__hint ${hintOpen ? "is-open" : ""}`}>
          <button type="button" className="sa-quiz__hint-toggle" onClick={onToggleHint} aria-expanded={hintOpen}>
            <span><StudentIcon name="tips_and_updates" size={18} role="decorative" /> Context clue</span>
            <StudentIcon name={hintOpen ? "expand_less" : "expand_more"} size={18} role="decorative" />
          </button>
          {hintOpen && <p>{hint}</p>}
        </StudentSection>
      )}

      <StudentSection variant="panel" className="sa-quiz__rail-card sa-quiz__question-map">
        <div className="sa-quiz__rail-heading"><span>Question map</span><span className="sa-quiz__map-legend"><i className="is-done" /> Done <i className="is-current" /> Current</span></div>
        <ol>
          {Array.from({ length: total }, (_, index) => {
            const result = resultAt(flow.results, index);
            const current = index === flow.index;
            return (
              <li key={index} className={`${current ? "is-current" : ""} ${result ? (result.correct ? "is-correct" : "is-incorrect") : "is-pending"}`}>
                {result ? <StudentIcon name={result.correct ? "check" : "close"} size={16} role="decorative" /> : index + 1}
              </li>
            );
          })}
        </ol>
      </StudentSection>
    </aside>
  );
}

function QuizQuestion({
  flow,
  question,
  entry,
  lessonLabel,
  pinyinDraft,
  setPinyinDraft,
  showingFeedback,
  lastResult,
  hint,
  onToggleHint,
  hintOpen,
}: {
  flow: ReturnType<typeof useVocabQuizFlow>;
  question: VocabQuizQuestion;
  entry?: VocabQuizEntry;
  lessonLabel: string;
  pinyinDraft: string;
  setPinyinDraft: (value: string) => void;
  showingFeedback: boolean;
  lastResult?: VocabQuizQuestionResult;
  hint?: string;
  onToggleHint: () => void;
  hintOpen: boolean;
}) {
  const assessment = question.kind === "assessment" ? question.assessment : undefined;
  const isFreeText = assessment?.answerFormat === "free_text";
  const pinyin = assessment?.pinyin || entry?.pinyin || toPinyin(question.word);
  const showReading = question.kind !== "pinyin" && assessment?.questionType !== "character_to_pinyin_typing";
  const audioUrl = assessment?.audioUrl || entry?.audioUrl;

  return (
    <section className="sa-quiz__question-column" aria-labelledby="quiz-question-title">
      <StudentSection variant="panel" className="sa-quiz__stimulus-card">
        <div className="sa-quiz__card-heading">
          <div><span className="sa-quiz__section-kicker"><i /> {questionTypeLabel(question)}</span><h2 id="quiz-question-title">{promptFor(question)}</h2></div>
          <span className="sa-quiz__source-label">{lessonLabel}</span>
        </div>
        <div className="sa-quiz__word-stage"><BilingualWord hanzi={question.word} pinyin={showReading ? pinyin : undefined} size="hero" /></div>
        <div className="sa-quiz__prompt-footer">
          {audioUrl ? <StudentAudioControl audioUrl={audioUrl} label="Listen to model" showDuration /> : <span />}
          {hint && <button type="button" className={`sa-quiz__hint-button ${hintOpen ? "is-open" : ""}`} onClick={onToggleHint} aria-expanded={hintOpen}><StudentIcon name="lightbulb" size={17} role="decorative" /> Context clue</button>}
        </div>
      </StudentSection>

      <div className="sa-quiz__answer-section">
        <div className="sa-quiz__answer-heading"><div><p className="sa-quiz__section-kicker">Select your answer</p><h3>{isFreeText ? "Type the reading" : "Choose one option"}</h3></div>{!showingFeedback && !isFreeText && <span className="sa-quiz__keyboard-hint">Keys 1–{question.options.length}</span>}</div>
        {!showingFeedback && isFreeText && (
          <div className="sa-quiz__input-block">
            <label htmlFor="sa-pinyin-input">Pinyin with tones</label>
            <input id="sa-pinyin-input" type="text" className="sa-quiz__input" value={pinyinDraft} onChange={(event) => setPinyinDraft(event.target.value)} placeholder="e.g. na3 li3" autoComplete="off" onKeyDown={(event) => { if (event.key === "Enter" && pinyinDraft.trim()) flow.choose(pinyinDraft.trim()); }} />
          </div>
        )}
        {!showingFeedback && !isFreeText && (
          <div className="sa-quiz__options" role="group" aria-label="Answer options">
            {question.options.map((option, index) => (
              <button key={option} type="button" className="sa-quiz__option" onClick={() => flow.choose(option)} aria-label={`Option ${index + 1}: ${option}`}>
                <span className="sa-quiz__option-index">{index + 1}</span><span className="sa-quiz__option-label">{option}</span><StudentIcon name="radio_button_unchecked" size={20} role="decorative" />
              </button>
            ))}
          </div>
        )}
        {showingFeedback && lastResult && (
          <div className={`sa-quiz__feedback ${lastResult.correct ? "is-correct" : "is-incorrect"}`} role="status">
            <StudentStatusPill tone={lastResult.correct ? "success" : "attention"} icon={lastResult.correct ? "check_circle" : "change_history"}>{lastResult.correct ? "Correct" : "Not quite"}</StudentStatusPill>
            <strong>{lastResult.correct ? "Good recognition." : "Keep this word in your next review."}</strong>
            {!lastResult.correct && lastResult.correctAnswer && <span>Answer: {lastResult.correctAnswer}</span>}
            {assessment?.explanation && <p>{assessment.explanation}</p>}
          </div>
        )}
        <div className="sa-quiz__actions">
          <div className="sa-quiz__action-note">{!showingFeedback && !isFreeText && <span>Select an option to check your answer.</span>}{!showingFeedback && isFreeText && <span>Use tone marks or tone numbers.</span>}</div>
          {showingFeedback ? <StudentButton variant="primary" iconTrailing="arrow_forward" onClick={flow.next}>Next question</StudentButton> : isFreeText ? <StudentButton variant="primary" disabled={!pinyinDraft.trim()} onClick={() => flow.choose(pinyinDraft.trim())}>Check answer</StudentButton> : null}
        </div>
      </div>
    </section>
  );
}

function ResultView({ flow, isLastTier }: { flow: ReturnType<typeof useVocabQuizFlow>; isLastTier: boolean }) {
  if (flow.view === "round-result" && flow.roundResult) {
    return <div className="sa-quiz__result-layout"><StudentSection variant="panel" className="sa-quiz__result-card"><StudentStatusPill tone={flow.roundResult.passed ? "success" : "attention"}>{flow.roundResult.passed ? "Passed" : "Not quite"}</StudentStatusPill><p className="sa-quiz__result-eyebrow">{ROUND_LABEL[flow.roundResult.tier]} complete</p><p className="sa-quiz__result-score">{flow.roundResult.correctCount} <span>/ {flow.roundResult.totalQuestions}</span></p><p className="sa-quiz__result-copy">{flow.roundResult.passed ? isLastTier ? "The speaking gate is ready for you." : "The next round is now unlocked." : `${flow.roundResult.starGap ?? 1} more correct answer${flow.roundResult.starGap === 1 ? "" : "s"} needed to pass this round.`}</p>{flow.roundResult.passed ? <StudentButton variant="primary" iconTrailing="arrow_forward" onClick={flow.continueToNext}>{isLastTier ? "Finish quiz" : "Continue"}</StudentButton> : <StudentButton variant="primary" icon="replay" onClick={flow.retry}>Try again</StudentButton>}</StudentSection></div>;
  }
  if (flow.view === "practice-result" && flow.practiceResult) {
    return <div className="sa-quiz__result-layout"><StudentSection variant="panel" className="sa-quiz__result-card"><StudentStatusPill tone="success">Practice complete</StudentStatusPill><p className="sa-quiz__result-eyebrow">{flow.practiceResult.mode === "maintenance_review" ? "Review today" : "Weak words"}</p><p className="sa-quiz__result-score">{flow.practiceResult.correctCount} <span>/ {flow.practiceResult.totalQuestions}</span></p><p className="sa-quiz__result-copy">Your practice result has been saved to your learning record.</p><StudentButton variant="primary" iconTrailing="arrow_back" onClick={flow.returnToModes}>Back to practice options</StudentButton></StudentSection></div>;
  }
  return null;
}

export default function VocabularyQuizPage({ topic, lessonLabel, onFinished }: VocabularyQuizPageProps) {
  const flow = useVocabQuizFlow({ topic, onFinished });
  const [pinyinDraft, setPinyinDraft] = useState("");
  const [hintOpen, setHintOpen] = useState(false);

  useEffect(() => {
    setPinyinDraft("");
    setHintOpen(false);
  }, [flow.index, flow.tierPos, flow.view, flow.question?.word]);

  if (flow.view === "loading") return <div className="sa-page-container sa-page-container--narrow"><p className="sa-quiz__loading" role="status">Loading practice options…</p></div>;

  const question = flow.question;
  const entry = entryFor(flow.entries, question);
  const assessment = question?.kind === "assessment" ? question.assessment : undefined;
  const lastResult = flow.results[flow.results.length - 1];
  const showingFeedback = Boolean(flow.selected !== null && question && lastResult?.word === question.word);
  const isLastTier = flow.tierPos === TIER_SEQUENCE.length - 1;

  return (
    <div className="sa-page-container sa-page-container--quiz">
      <QuizHeader flow={flow} lessonLabel={lessonLabel} question={question} />
      {flow.view === "mode-select" ? <ModePicker flow={flow} /> : flow.view === "round-result" || flow.view === "practice-result" ? <ResultView flow={flow} isLastTier={isLastTier} /> : question ? (
        <div className="sa-quiz__workspace">
          <QuizQuestion flow={flow} question={question} entry={entry} lessonLabel={lessonLabel} pinyinDraft={pinyinDraft} setPinyinDraft={setPinyinDraft} showingFeedback={showingFeedback} lastResult={lastResult} hint={assessment?.explanation} hintOpen={hintOpen} onToggleHint={() => setHintOpen((open) => !open)} />
          <QuizRail flow={flow} hint={assessment?.explanation} hintOpen={hintOpen} onToggleHint={() => setHintOpen((open) => !open)} />
        </div>
      ) : null}
    </div>
  );
}
