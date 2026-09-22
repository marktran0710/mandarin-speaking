import type { ConversationState } from "./StoryRecorder/conversationCoordinator";
import type { ConversationTurn } from "./StoryRecorder/conversation";

interface ConversationTurnProgressProps {
  turns: readonly ConversationTurn[];
  state: ConversationState;
}

export default function ConversationTurnProgress({
  turns,
  state,
}: ConversationTurnProgressProps) {
  const activeTurnIndex = state.step === "summary" ? turns.length : state.turnIndex;
  const completedTurns = state.step === "summary"
    ? turns.length
    : state.step === "system"
      ? state.turnIndex
      : state.turnIndex;
  const label = state.step === "summary"
    ? "Conversation complete"
    : `Turn ${Math.min(activeTurnIndex + 1, turns.length)} of ${turns.length}`;

  return (
    <div className="conversation-turn-progress" aria-label="Conversation progress">
      <div className="conversation-turn-progress__copy">
        <strong>{label}</strong>
        <span>{state.step === "summary" ? "Review complete" : `${state.step === "selfEval" || state.step === "feedback" ? "Review your response" : state.step === "student" ? "Your response" : "Listen first"}`}</span>
      </div>
      <ol className="conversation-turn-progress__rail">
        {turns.map((turn, index) => (
          <li
            key={turn.id}
            className={index < completedTurns ? "is-complete" : index === activeTurnIndex ? "is-current" : undefined}
            aria-current={index === activeTurnIndex ? "step" : undefined}
          >
            <span aria-hidden="true">{index + 1}</span>
            <span className="student-visually-hidden">{turn.speaker} turn {index + 1}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
