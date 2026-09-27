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
import StudentSystemText from "@shared/ui/student/StudentSystemText";
import type { StudentUiCopyKey } from "../../i18n/student-ui-copy";
import "./VocabularyQuizPage.css";

interface VocabularyQuizPageProps {
  topic: Topic;
  lessonLabel: string;
  onFinished: () => void;
  onStartPractice?: (practice: "story-speaking" | "conversation") => void;
}

const ROUND_DESCRIPTION_KEYS: Record<TierMode, "roundOneDescription" | "roundTwoDescription" | "roundThreeDescription"> = {
  tier1: "roundOneDescription",
  tier2: "roundTwoDescription",
  tier3: "roundThreeDescription",
};

function roundName(mode: VocabQuizMode | null, tierPos: number): string {
  const tier = mode && mode in ROUND_LABEL ? mode as TierMode : TIER_SEQUENCE[tierPos];
  return tier === "tier1" ? "認識" : tier === "tier2" ? "說出" : "運用";
}

function roundCopyKey(mode: VocabQuizMode | null, tierPos: number): StudentUiCopyKey {
  const tier = mode && mode in ROUND_LABEL ? mode as TierMode : TIER_SEQUENCE[tierPos];
  return tier === "tier1" ? "knowIt" : tier === "tier2" ? "sayIt" : "useIt";
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
      <div className="sa-quiz__header-meta" aria-label="測驗狀態">
        {question && (
          <span className="sa-quiz__meta-chip">
            <StudentIcon name="quiz" size={16} role="decorative" />
            第 {flow.index + 1} / {total} 題
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
        aria-label="測驗進度"
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
  const tierCopyKey = roundCopyKey(flow.mode, flow.tierPos);
  const weakCount = flow.weakEntries.length || flow.interimReviewEntries.length;
  const dueCount = flow.dueWords.length;

  return (
    <div className="sa-quiz__mode-layout">
      <section className="sa-quiz__mode-main" aria-labelledby="quiz-mode-title">
        <div className="sa-quiz__mode-intro">
          <div>
            <StudentStatusPill tone="info" icon="route"><StudentSystemText k="guidedPractice" withinControl /></StudentStatusPill>
            <h2 id="quiz-mode-title"><StudentSystemText k="choosePracticePath" /></h2>
            <p><StudentSystemText k="buildWordFoundation" /></p>
          </div>
          <div className="sa-quiz__star-summary" aria-label={`${flow.stars} of 3 stars earned`}>
            <StudentIcon name="hotel_class" size={20} role="decorative" filled />
            <strong>{flow.stars}</strong><span>/ 3 顆星</span>
          </div>
        </div>

        <div className="sa-quiz__mode-grid">
          <StudentSection variant="panel" className="sa-quiz__mode-card sa-quiz__mode-card--primary">
            <div className="sa-quiz__mode-index">01</div>
            <div className="sa-quiz__mode-copy">
              <p className="sa-quiz__mode-kicker"><StudentSystemText k="diagnosticPath" /></p>
              <h3><StudentSystemText k={tierCopyKey} /></h3>
              <p><StudentSystemText k={ROUND_DESCRIPTION_KEYS[tier]} /></p>
              <div className="sa-quiz__mode-detail"><StudentIcon name="lock_open" size={15} role="decorative" /><span><StudentSystemText k="roundsUnlockInOrder" /></span></div>
            </div>
            <StudentButton variant="primary" iconTrailing="arrow_forward" onClick={flow.startTier}>
              <><StudentSystemText k="start" withinControl /> <StudentSystemText k={tierCopyKey} withinControl /></>
            </StudentButton>
          </StudentSection>

          <StudentSection variant="panel" className="sa-quiz__mode-card">
            <div className="sa-quiz__mode-index">02</div>
            <div className="sa-quiz__mode-copy">
              <p className="sa-quiz__mode-kicker"><StudentSystemText k="personalisedPractice" /></p>
              <h3><StudentSystemText k="weakWords" /></h3>
              <p><StudentSystemText k="practiceFromRecord" /></p>
              <div className="sa-quiz__mode-detail"><StudentIcon name="psychology" size={15} role="decorative" /><span>{weakCount > 0 ? `${weakCount} 個詞語可以練習` : <StudentSystemText k="noWordsQueued" />}</span></div>
            </div>
            <StudentButton variant="secondary" icon="fitness_center" disabled={weakCount === 0} onClick={flow.startWeakWords}>
              <StudentSystemText k="practiceWeakWords" withinControl />
            </StudentButton>
          </StudentSection>

          <StudentSection variant="panel" className="sa-quiz__mode-card">
            <div className="sa-quiz__mode-index">03</div>
            <div className="sa-quiz__mode-copy">
              <p className="sa-quiz__mode-kicker"><StudentSystemText k="spacedReview" /></p>
              <h3><StudentSystemText k="reviewToday" /></h3>
              <p><StudentSystemText k="dueSchedule" /></p>
              <div className="sa-quiz__mode-detail"><StudentIcon name="event_repeat" size={15} role="decorative" /><span>{dueCount > 0 ? `${dueCount} 個詞語到期` : <StudentSystemText k="nothingDue" />}</span></div>
            </div>
            <StudentButton variant="secondary" icon="schedule" disabled={dueCount === 0} onClick={flow.startDueReview}>
              <StudentSystemText k="reviewDueWords" withinControl />
            </StudentButton>
          </StudentSection>
        </div>
      </section>

       <aside className="sa-quiz__mode-rail" aria-label="練習概覽">
        <StudentSection variant="panel" className="sa-quiz__rail-card">
          <div className="sa-quiz__rail-heading"><StudentSystemText k="practiceOverview" /><StudentStatusPill tone="success"><StudentSystemText k="activeSession" withinControl /></StudentStatusPill></div>
          <dl className="sa-quiz__overview-list">
             <div><dt><StudentSystemText k="lessonWords" /></dt><dd>{flow.entries.length}</dd></div>
             <div><dt><StudentSystemText k="starsEarned" /></dt><dd>{flow.stars} / 3</dd></div>
             <div><dt><StudentSystemText k="speakingGate" /></dt><dd><StudentSystemText k={flow.stars >= 3 ? "open" : "locked"} /></dd></div>
          </dl>
        </StudentSection>
        <StudentSection variant="tinted" className="sa-quiz__rail-card sa-quiz__round-guide">
          <div className="sa-quiz__rail-heading"><StudentSystemText k="diagnosticSequence" /><StudentIcon name="stairs" size={18} role="decorative" /></div>
          <ol>
            {TIER_SEQUENCE.map((round, index) => (
              <li key={round} className={index < flow.tierPos ? "is-complete" : index === flow.tierPos ? "is-current" : ""}>
                <span>{index + 1}</span><div><strong><StudentSystemText k={round === "tier1" ? "knowIt" : round === "tier2" ? "sayIt" : "useIt"} /></strong><small><StudentSystemText k={ROUND_DESCRIPTION_KEYS[round]} /></small></div>
              </li>
            ))}
          </ol>
        </StudentSection>
      </aside>
    </div>
  );
}

function ResultView({ flow, isLastTier }: { flow: ReturnType<typeof useVocabQuizFlow>; isLastTier: boolean }) {
  if (flow.view === "round-result" && flow.roundResult) {
    return (
      <div className="sa-quiz__result-layout">
        <StudentSection variant="panel" className="sa-quiz__result-card">
          <StudentStatusPill tone={flow.roundResult.passed ? "success" : "attention"}><StudentSystemText k={flow.roundResult.passed ? "completed" : "notQuite"} withinControl /></StudentStatusPill>
          <p className="sa-quiz__result-eyebrow"><StudentSystemText k={flow.roundResult.tier === "tier1" ? "knowIt" : flow.roundResult.tier === "tier2" ? "sayIt" : "useIt"} /> 完成</p>
          <p className="sa-quiz__result-score">{flow.roundResult.correctCount} <span>/ {flow.roundResult.totalQuestions}</span></p>
           <p className="sa-quiz__result-copy">{flow.roundResult.passed ? isLastTier ? <StudentSystemText k="vocabularyGateOpen" /> : <StudentSystemText k="nextRoundUnlocked" /> : `${flow.roundResult.starGap ?? 1} 題答對後即可通過這一輪。`}</p>
          {flow.roundResult.passed ? isLastTier ? (
            <div className="sa-quiz__practice-choice" role="group" aria-label="Choose a practice path">
               <StudentButton variant="primary" iconTrailing="arrow_forward" onClick={() => flow.choosePractice("story-speaking")}><StudentSystemText k="storySpeaking" withinControl /></StudentButton>
               <StudentButton variant="secondary" iconTrailing="arrow_forward" onClick={() => flow.choosePractice("conversation")}><StudentSystemText k="conversation" withinControl /></StudentButton>
             </div>
           ) : <StudentButton variant="primary" iconTrailing="arrow_forward" onClick={flow.continueToNext}><StudentSystemText k="continue" withinControl /></StudentButton> : <StudentButton variant="primary" icon="replay" onClick={flow.retry}><StudentSystemText k="retry" withinControl /></StudentButton>}
        </StudentSection>
      </div>
    );
  }
  if (flow.view === "practice-result" && flow.practiceResult) {
    return (
      <div className="sa-quiz__result-layout">
        <StudentSection variant="panel" className="sa-quiz__result-card">
           <StudentStatusPill tone="success"><StudentSystemText k="practiceComplete" withinControl /></StudentStatusPill>
           <p className="sa-quiz__result-eyebrow"><StudentSystemText k={flow.practiceResult.mode === "maintenance_review" ? "reviewToday" : "weakWords"} /></p>
          <p className="sa-quiz__result-score">{flow.practiceResult.correctCount} <span>/ {flow.practiceResult.totalQuestions}</span></p>
           <p className="sa-quiz__result-copy"><StudentSystemText k="savedToLearningRecord" /></p>
           <StudentButton variant="primary" iconTrailing="arrow_back" onClick={flow.returnToModes}><StudentSystemText k="backToPracticeOptions" withinControl /></StudentButton>
        </StudentSection>
      </div>
    );
  }
  return null;
}

export default function VocabularyQuizPage({ topic, lessonLabel, onFinished, onStartPractice }: VocabularyQuizPageProps) {
  const flow = useVocabQuizFlow({ topic, onFinished, onStartPractice });
  const [draftAnswer, setDraftAnswer] = useState<string | null>(null);
  const [pinyinDraft, setPinyinDraft] = useState("");

  useEffect(() => {
    setDraftAnswer(null);
    setPinyinDraft("");
  }, [flow.index, flow.tierPos, flow.view, flow.question?.word]);

  const header = (
    <StudentPageHeader
      eyebrowKey="study"
      context={<><span lang="zh-Hant">{lessonLabel}</span> · <StudentSystemText k="vocabularyQuizTitle" /></>}
      titleKey="vocabularyQuizTitle"
      aside={flow.entries.length > 0 ? <span className="sa-quiz__round-tag">{roundName(flow.mode, flow.tierPos)}</span> : undefined}
    />
  );

  if (flow.entries.length === 0) {
    return (
      <StudentPage
        layout="task"
        header={header}
        state="empty"
        emptyTitle={<StudentSystemText k="noQuiz" />}
        emptyAction={<StudentButton variant="primary" iconTrailing="arrow_forward" onClick={onFinished}><StudentSystemText k="continueToSpeaking" withinControl /></StudentButton>}
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
      {flow.view === "mode-select" ? <ModePicker flow={flow} /> : flow.view === "round-result" || flow.view === "practice-result" ? <ResultView flow={flow} isLastTier={isLastTier} /> : question ? (
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
