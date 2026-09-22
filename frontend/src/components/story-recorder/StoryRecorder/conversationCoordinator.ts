import {
  normalizeConversationTurns,
  type ConversationTurn,
} from "./conversation";

export type ConversationStep = "system" | "student" | "selfEval" | "feedback" | "summary";

export interface ConversationState {
  /** Index of the active turn in the normalized conversation list. */
  turnIndex: number;
  step: ConversationStep;
  studentRecordingId?: string;
}

export type ConversationEvent =
  | { type: "systemAudioCompleted" }
  | { type: "studentRecordingCompleted"; recordingId: string }
  | { type: "selfEvaluationSubmitted" }
  | { type: "selfEvaluationSkipped" }
  | { type: "feedbackCompleted" };

export interface ConversationTransition {
  state: ConversationState;
  accepted: boolean;
}

/**
 * Creates the first state only for an explicit, valid conversation. Returning
 * null is the compatibility signal for the existing scene-based recorder.
 */
export function createConversationState(value: unknown): ConversationState | null {
  const turns = normalizeConversationTurns(value);
  return turns ? { turnIndex: 0, step: "system" } : null;
}

export function currentConversationTurn(
  state: ConversationState,
  turns: readonly ConversationTurn[],
): ConversationTurn | null {
  if (state.step === "summary") return null;
  return turns[state.turnIndex] ?? null;
}

export function isStudentRecordingStep(state: ConversationState): boolean {
  return state.step === "student";
}

export function shouldAnalyzeConversationTurn(state: ConversationState): boolean {
  return state.step === "student";
}

/**
 * Applies one user/system event. Invalid events are rejected without changing
 * state, which lets a UI disable premature actions without risking a skipped
 * turn when an event arrives late.
 */
export function transitionConversation(
  state: ConversationState,
  event: ConversationEvent,
  turns: readonly ConversationTurn[],
): ConversationTransition {
  if (state.step === "summary") return { state, accepted: false };

  switch (event.type) {
    case "systemAudioCompleted":
      if (state.step !== "system" || turns[state.turnIndex]?.speaker !== "system") {
        return { state, accepted: false };
      }
      return {
        state: { turnIndex: state.turnIndex + 1, step: "student" },
        accepted: true,
      };

    case "studentRecordingCompleted":
      if (
        state.step !== "student" ||
        turns[state.turnIndex]?.speaker !== "student" ||
        event.recordingId.trim() === ""
      ) {
        return { state, accepted: false };
      }
      return {
        state: {
          turnIndex: state.turnIndex,
          step: "selfEval",
          studentRecordingId: event.recordingId,
        },
        accepted: true,
      };

    case "selfEvaluationSubmitted":
    case "selfEvaluationSkipped":
      if (state.step !== "selfEval") return { state, accepted: false };
      return { state: { ...state, step: "feedback" }, accepted: true };

    case "feedbackCompleted": {
      if (state.step !== "feedback") return { state, accepted: false };
      const nextTurnIndex = state.turnIndex + 1;
      if (nextTurnIndex >= turns.length) {
        return {
          state: { turnIndex: turns.length, step: "summary" },
          accepted: true,
        };
      }
      return {
        state: { turnIndex: nextTurnIndex, step: "system" },
        accepted: true,
      };
    }
  }
}
