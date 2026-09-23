import type { ConversationState } from "./StoryRecorder/conversationCoordinator";
import type { ConversationTurn } from "./StoryRecorder/conversation";

interface ConversationTurnProgressProps {
  turns: readonly ConversationTurn[];
  state: ConversationState;
}

/** Dual Speaking Modes plan, Epic 5: student-facing progress counts
 * EXCHANGES (one system + one student turn), never raw internal turns - a
 * 4-exchange conversation is "Exchange 2 of 4", not "Turn 3 of 8". Turns
 * strictly alternate system/student (enforced by normalizeConversationTurns),
 * so exchange index is just raw turn index halved. */
export default function ConversationTurnProgress({
  turns,
  state,
}: ConversationTurnProgressProps) {
  const exchangeCount = Math.floor(turns.length / 2);
  const activeExchangeIndex = state.step === "summary"
    ? exchangeCount
    : Math.min(Math.floor(state.turnIndex / 2), exchangeCount - 1);
  const completedExchanges = state.step === "summary" ? exchangeCount : activeExchangeIndex;
  const label = state.step === "summary"
    ? "Conversation complete"
    : `Exchange ${activeExchangeIndex + 1} of ${exchangeCount}`;

  return (
    <div className="conversation-turn-progress" aria-label="Conversation progress">
      <div className="conversation-turn-progress__copy">
        <strong>{label}</strong>
        <span>{state.step === "summary" ? "Review complete" : `${state.step === "selfEval" || state.step === "feedback" ? "Review your response" : state.step === "student" ? "Your response" : "Listen first"}`}</span>
      </div>
      <ol className="conversation-turn-progress__rail">
        {Array.from({ length: exchangeCount }, (_, index) => (
          <li
            key={turns[index * 2]?.id ?? index}
            className={index < completedExchanges ? "is-complete" : index === activeExchangeIndex ? "is-current" : undefined}
            aria-current={index === activeExchangeIndex ? "step" : undefined}
          >
            <span aria-hidden="true">{index + 1}</span>
            <span className="student-visually-hidden">Exchange {index + 1}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
