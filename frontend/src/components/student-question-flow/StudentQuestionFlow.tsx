import type { ReactNode } from "react";
import "./StudentQuestionFlow.css";
import {
  StudentSection,
  StudentSectionBody,
  StudentSectionFooter,
} from "../student-workspace/student-section";

type StudentQuestionFlowProps = {
  ariaLabel: string;
  topbar?: ReactNode;
  prompt: ReactNode;
  answers: ReactNode;
  actions?: ReactNode;
  questionKey?: string | number;
  className?: string;
};

/**
 * Presentation-only frame for an active student question. Domain adapters own
 * prompts, answer behavior, progress semantics, and completion effects.
 */
export function StudentQuestionFlow({
  ariaLabel,
  topbar,
  prompt,
  answers,
  actions,
  questionKey,
  className = "",
}: StudentQuestionFlowProps) {
  return (
    <StudentSection
      variant="task"
      className={`student-question-flow story-vocab-quiz vocab-quiz-question-screen ${className}`.trim()}
      aria-label={ariaLabel}
    >
      <div className="vocab-quiz-topbar">{topbar}</div>
      <StudentSectionBody layout="task" className="vocab-quiz-content" key={questionKey}>
        <div className="vocab-quiz-question-panel">
          <div className="vocab-quiz-header">{prompt}</div>
        </div>
        <div className="vocab-quiz-answer-panel">
          {answers}
          <StudentSectionFooter align="center" className="vocab-quiz-actions">
            {actions}
          </StudentSectionFooter>
        </div>
      </StudentSectionBody>
    </StudentSection>
  );
}
