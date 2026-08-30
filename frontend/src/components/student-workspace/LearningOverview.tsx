import { BiLabel, BiText } from "../BiLabel";
import type { QuizGateState, WorkspaceTopicSummary } from "../../types/studentWorkspace";
import ActionButton from "../../shared/ui/ActionButton";
import StudentIcon from "../StudentIcon";

interface LearningOverviewProps {
  topicSummary?: WorkspaceTopicSummary;
  onStartActivity: () => void;
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

export default function LearningOverview({ topicSummary, onStartActivity }: LearningOverviewProps) {
  const gate = topicSummary?.quizGate ?? {
    status: "unavailable" as const,
    reason: "No activities are available yet.",
  };
  const startLabel = gate.status === "required" ? "Take quiz to begin" : "Start activity";

  return (
    <section className="workspace-quick-start" aria-label="Learning overview">
      <div className="workspace-quick-start-copy">
        <p className="workspace-section-kicker">
          <BiLabel zh="開始練習" en="Start practice" />
        </p>
        <h2>{topicSummary ? topicSummary.topic.name : "No activity is ready yet."}</h2>
        <p>
          <BiText
            zh="完成小測驗後，就可以開始口說練習。"
            pinyin="Wánchéng xiǎo cèyàn hòu, jiù kěyǐ kāishǐ kǒushuō liànxí."
            en="Finish the short quiz before speaking practice."
          />
        </p>
      </div>
      <div className="workspace-quick-start-action">
        <QuizGateStatus gate={gate} />
        <ActionButton
          type="button"
          variant="primary"
          onClick={onStartActivity}
          disabled={!topicSummary || gate.status === "unavailable"}
        >
          <span>{startLabel}</span>
          <StudentIcon name="arrow-right" size={16} aria-hidden="true" />
        </ActionButton>
      </div>
    </section>
  );
}
