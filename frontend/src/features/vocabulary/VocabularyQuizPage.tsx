import { useEffect, useState } from "react";
import type { Topic } from "@entities/topic";
import type { TierMode } from "@entities/vocabulary";
import {
  type VocabQuizMode,
  type VocabQuizQuestion,
} from "@entities/vocabulary";
import { useVocabQuizFlow } from "./hooks/useVocabQuizFlow";
import { ROUND_LABEL, TIER_SEQUENCE } from "./model/tierRounds";
import QuizQuestionSurface from "./quiz/QuestionSurface";
import QuizRail from "./quiz/Rail";
import { resultForQuestion } from "./quiz/questionModel";
import StudentButton from "@shared/ui/student/StudentButton";
import StudentIcon from "@shared/ui/student/StudentIcon";
import StudentPage from "@shared/ui/student/StudentPage";
import StudentPageHeader from "@shared/ui/student/StudentPageHeader";
import StudentSection from "@shared/ui/student/StudentSection";
import StudentStatusPill from "@shared/ui/student/StudentStatusPill";
import "./VocabularyQuizPage.css";

interface VocabularyQuizPageProps {
  topic: Topic;
  lessonLabel: string;
  onFinished: () => void;
  onStartPractice?: (practice: "story-speaking" | "conversation") => void;
  hasConversation?: boolean;
}

const ROUND_DESCRIPTIONS: Record<TierMode, string> = {
  tier1: "Recognise the meaning of each lesson word.",
  tier2: "Recall the reading and form of each word.",
  tier3: "Use the words in context before speaking practice.",
};

function roundName(mode: VocabQuizMode | null, tierPos: number): string {
  if (mode && mode in ROUND_LABEL) return ROUND_LABEL[mode as TierMode];
  return ROUND_LABEL[TIER_SEQUENCE[tierPos]];
}

function formatTime(milliseconds: number): string {
  const seconds = Math.max(0, Math.ceil(milliseconds / 1000));
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

function QuizStatusBar({
  flow,
  question,
}: {
  flow: ReturnType<typeof useVocabQuizFlow>;
  question: VocabQuizQuestion | null;
}) {
  const total = flow.questionLimit ?? flow.entries.length;
  const completed = flow.results.length;
  const progress = total > 0 ? Math.min(100, (completed / total) * 100) : 0;

  return (
    <div className="sa-quiz__status-bar">
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

function ResultView({ flow, isLastTier, hasConversation }: { flow: ReturnType<typeof useVocabQuizFlow>; isLastTier: boolean; hasConversation: boolean }) {
  if (flow.view === "round-result" && flow.roundResult) {
    return (
      <div className="sa-quiz__result-layout">
        <StudentSection variant="panel" className="sa-quiz__result-card">
          <StudentStatusPill tone={flow.roundResult.passed ? "success" : "attention"}>{flow.roundResult.passed ? "Passed" : "Not quite"}</StudentStatusPill>
          <p className="sa-quiz__result-eyebrow">{ROUND_LABEL[flow.roundResult.tier]} complete</p>
          <p className="sa-quiz__result-score">{flow.roundResult.correctCount} <span>/ {flow.roundResult.totalQuestions}</span></p>
          <p className="sa-quiz__result-copy">{flow.roundResult.passed ? isLastTier ? "Your vocabulary gate is open. Choose one practice path to continue." : "The next round is now unlocked." : `${flow.roundResult.starGap ?? 1} more correct answer${flow.roundResult.starGap === 1 ? "" : "s"} needed to pass this round.`}</p>
          {flow.roundResult.passed ? isLastTier ? (
            <div className="sa-quiz__practice-choice" role="group" aria-label="Choose a practice path">
              <StudentButton variant="primary" iconTrailing="arrow_forward" onClick={() => flow.choosePractice("story-speaking")}>Story Speaking</StudentButton>
              {hasConversation && <StudentButton variant="secondary" iconTrailing="arrow_forward" onClick={() => flow.choosePractice("conversation")}>Conversation Practice</StudentButton>}
            </div>
          ) : <StudentButton variant="primary" iconTrailing="arrow_forward" onClick={flow.continueToNext}>Continue</StudentButton> : <StudentButton variant="primary" icon="replay" onClick={flow.retry}>Try again</StudentButton>}
        </StudentSection>
      </div>
    );
  }
  if (flow.view === "practice-result" && flow.practiceResult) {
    return (
      <div className="sa-quiz__result-layout">
        <StudentSection variant="panel" className="sa-quiz__result-card">
          <StudentStatusPill tone="success">Practice complete</StudentStatusPill>
          <p className="sa-quiz__result-eyebrow">{flow.practiceResult.mode === "maintenance_review" ? "Review today" : "Weak words"}</p>
          <p className="sa-quiz__result-score">{flow.practiceResult.correctCount} <span>/ {flow.practiceResult.totalQuestions}</span></p>
          <p className="sa-quiz__result-copy">Your practice result has been saved to your learning record.</p>
          <StudentButton variant="primary" iconTrailing="arrow_back" onClick={flow.returnToModes}>Back to practice options</StudentButton>
        </StudentSection>
      </div>
    );
  }
  return null;
}

export default function VocabularyQuizPage({ topic, lessonLabel, onFinished, onStartPractice, hasConversation = false }: VocabularyQuizPageProps) {
  const flow = useVocabQuizFlow({ topic, onFinished, onStartPractice });
  const [draftAnswer, setDraftAnswer] = useState<string | null>(null);
  const [pinyinDraft, setPinyinDraft] = useState("");

  useEffect(() => {
    setDraftAnswer(null);
    setPinyinDraft("");
  }, [flow.index, flow.tierPos, flow.view, flow.question?.word]);

  const header = (
    <StudentPageHeader
      eyebrowZh={`學習 · ${lessonLabel} · 詞彙測驗`}
      eyebrowEn={`Study · ${lessonLabel} · Vocabulary Quiz`}
      titleZh="詞彙測驗"
      titleEn="Vocabulary Quiz"
      aside={flow.entries.length > 0 ? <span className="sa-quiz__round-tag">{roundName(flow.mode, flow.tierPos)}</span> : undefined}
    />
  );

  if (flow.entries.length === 0) {
    return (
      <StudentPage
        layout="task"
        header={header}
        state="empty"
        emptyTitle={<><span lang="zh-Hant">此課程沒有測驗</span> · No quiz for this lesson</>}
        emptyAction={<StudentButton variant="primary" iconTrailing="arrow_forward" onClick={onFinished}>Continue to Story Speaking</StudentButton>}
      />
    );
  }

  if (flow.view === "loading") return <StudentPage layout="task" header={header} state="loading" />;

  const question = flow.question;
  const entry = question ? flow.entries.find((candidate) => candidate.word === question.word) : undefined;
  const assessment = question?.kind === "assessment" ? question.assessment : undefined;
  const lastResult = question ? resultForQuestion(flow.results, flow.index, question.word) : undefined;
  const showingFeedback = Boolean(flow.selected !== null && lastResult);
  const submitAnswer = () => {
    if (!question || flow.selected !== null) return;
    const answer = assessment?.answerFormat === "free_text" || question.kind === "pinyin"
      ? pinyinDraft.trim()
      : draftAnswer;
    if (answer) flow.choose(answer);
  };
  const isLastTier = flow.tierPos === TIER_SEQUENCE.length - 1;

  return (
    <StudentPage layout="task" wide header={header}>
      <QuizStatusBar flow={flow} question={question} />
      {flow.view === "mode-select" ? <ModePicker flow={flow} /> : flow.view === "round-result" || flow.view === "practice-result" ? <ResultView flow={flow} isLastTier={isLastTier} hasConversation={hasConversation} /> : question ? (
        <div className="sa-quiz__workspace">
          <QuizQuestionSurface
            question={question}
            entry={entry}
            entries={flow.entries}
            lessonLabel={lessonLabel}
            draftAnswer={draftAnswer}
            onDraftAnswerChange={setDraftAnswer}
            pinyinDraft={pinyinDraft}
            onPinyinChange={setPinyinDraft}
            showingFeedback={showingFeedback}
            lastResult={lastResult}
            onSubmit={submitAnswer}
            onNext={flow.next}
          />
          <QuizRail flow={flow} question={question} />
        </div>
      ) : null}
    </StudentPage>
  );
}
