import StudentIcon from "../StudentIcon";
import { BiLabel, BiText } from "../BiLabel";
import type { LearningSummary, QuizGateState, WorkspaceTopicSummary } from "../../types/studentWorkspace";
import ActionButton from "../../shared/ui/ActionButton";
import ProgressBar from "../../shared/ui/ProgressBar";

interface LearningOverviewProps {
  summary: LearningSummary;
  topicSummary?: WorkspaceTopicSummary;
  onStartActivity: () => void;
  onOpenProgress: () => void;
  onOpenPractice: () => void;
}

function progressLabel(value: number): string {
  return `${Math.max(0, Math.min(100, Math.round(value)))}%`;
}

export function QuizGateStatus({ gate }: { gate: QuizGateState }) {
  if (gate.status === "completed") {
    return (
      <span className="workspace-gate workspace-gate-complete">
        <span aria-hidden="true">✓</span>
        <span>
          <strong>Quiz complete</strong>
          <small>Ready to start speaking practice</small>
        </span>
      </span>
    );
  }

  if (gate.status === "required") {
    return (
      <span className="workspace-gate workspace-gate-required">
        <span aria-hidden="true">!</span>
        <span>
          <strong>Quiz required first</strong>
          <small>{gate.reason}</small>
        </span>
      </span>
    );
  }

  return (
    <span className="workspace-gate workspace-gate-unavailable">
      <span aria-hidden="true">—</span>
      <span>
        <strong>No quiz for this activity</strong>
        <small>{gate.reason}</small>
      </span>
    </span>
  );
}

export function ProgressSnapshot({ summary }: { summary: LearningSummary }) {
  return (
    <section className="workspace-overview-card workspace-progress-card" aria-labelledby="workspace-progress-title">
      <div className="workspace-card-heading">
        <span className="workspace-card-icon workspace-card-icon-jade" aria-hidden="true">
          <StudentIcon name="chart" size={22} />
        </span>
        <div>
          <h2 id="workspace-progress-title">學習進度</h2>
          <p>Progress snapshot</p>
        </div>
      </div>
      <div className="workspace-progress-value-row">
        <strong>{progressLabel(summary.lessonProgress)}</strong>
        <span>activity progress</span>
      </div>
      <ProgressBar value={summary.lessonProgress} label={`${progressLabel(summary.lessonProgress)} activity progress`} />
      <dl className="workspace-metric-list">
        <div>
          <dt>Today</dt>
          <dd>{summary.todayGoal.completed}/{summary.todayGoal.total}</dd>
        </div>
        <div>
          <dt>Quiz words</dt>
          <dd>{summary.wordsToPractice}</dd>
        </div>
      </dl>
    </section>
  );
}

export function ContinueLearningCard({ summary, onContinue }: { summary: LearningSummary; onContinue: () => void }) {
  const target = summary.continueTarget;
  return (
    <section className="workspace-overview-card workspace-continue-card" aria-labelledby="workspace-continue-title">
      <div className="workspace-card-heading">
        <span className="workspace-card-icon workspace-card-icon-amber" aria-hidden="true">
          <StudentIcon name="play" size={22} />
        </span>
        <div>
          <h2 id="workspace-continue-title">繼續學習</h2>
          <p>Continue learning</p>
        </div>
      </div>
      {target ? (
        <>
          <strong className="workspace-continue-title">{target.label}</strong>
          <div className="workspace-continue-meta">
            <span>{progressLabel(target.progress)} recorded</span>
            <span aria-hidden="true">·</span>
            <span>Keep going slowly</span>
          </div>
          <ProgressBar value={target.progress} tone="amber" label={`${progressLabel(target.progress)} recorded`} />
        </>
      ) : (
        <p className="workspace-empty-copy">Start one activity and it will appear here for your next visit.</p>
      )}
      <ActionButton type="button" variant="secondary" onClick={onContinue}>
        {target ? "Continue activity" : "Browse activities"}
        <span aria-hidden="true">→</span>
      </ActionButton>
    </section>
  );
}

export function VocabularyPreview({ topicSummary, onOpenPractice }: { topicSummary?: WorkspaceTopicSummary; onOpenPractice: () => void }) {
  const words = topicSummary?.topic.vocabulary[0]?.slice(0, 5) ?? [];
  return (
    <section className="workspace-overview-card workspace-vocabulary-card" aria-labelledby="workspace-vocabulary-title">
      <div className="workspace-card-heading">
        <span className="workspace-card-icon workspace-card-icon-paper" aria-hidden="true">
          <StudentIcon name="stories" size={22} />
        </span>
        <div>
          <h2 id="workspace-vocabulary-title">最近的詞語</h2>
          <p>Vocabulary preview</p>
        </div>
        <button type="button" className="workspace-card-link" onClick={onOpenPractice}>View all</button>
      </div>
      {words.length > 0 ? (
        <div className="workspace-word-list">
          {words.map((word) => <span key={word} className="workspace-word-chip">{word}</span>)}
        </div>
      ) : (
        <p className="workspace-empty-copy">Vocabulary will appear after your teacher publishes an activity.</p>
      )}
      {topicSummary && <QuizGateStatus gate={topicSummary.quizGate} />}
    </section>
  );
}

export default function LearningOverview({
  summary,
  topicSummary,
  onStartActivity,
  onOpenProgress,
  onOpenPractice,
}: LearningOverviewProps) {
  const gate = topicSummary?.quizGate ?? { status: "unavailable" as const, reason: "No activities are available yet." };
  const startLabel = gate.status === "required" ? "Take quiz to begin" : "Start activity";

  return (
    <section className="workspace-overview" aria-label="Learning overview">
      <div className="workspace-overview-intro">
        <div>
          <p className="workspace-section-kicker"><BiLabel zh="今天慢慢學" pinyin="Jīntiān mànmàn xué" en="Today’s learning" /></p>
          <h2>Small steps, clear progress.</h2>
          <p><BiText zh="先看看今天要做什麼，再開始練習。" pinyin="Xiān kànkan jīntiān yào zuò shénme." en="See what is waiting for you, then begin when you are ready." /></p>
        </div>
        <div className="workspace-overview-cta">
          <QuizGateStatus gate={gate} />
          <ActionButton
            type="button"
            variant="primary"
            onClick={onStartActivity}
            disabled={!topicSummary}
          >
            <span>{startLabel}</span>
            <span aria-hidden="true">→</span>
          </ActionButton>
        </div>
      </div>
      <div className="workspace-overview-grid">
        <ProgressSnapshot summary={summary} />
        <ContinueLearningCard summary={summary} onContinue={onStartActivity} />
        <VocabularyPreview topicSummary={topicSummary} onOpenPractice={onOpenPractice} />
      </div>
      <button type="button" className="workspace-progress-link" onClick={onOpenProgress}>
        <span>Open full progress</span>
        <span aria-hidden="true">→</span>
      </button>
    </section>
  );
}
