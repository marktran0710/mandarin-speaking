import { describe, expect, it } from "vitest";
import {
  createConversationState,
  currentConversationTurn,
  isStudentRecordingStep,
  shouldAnalyzeConversationTurn,
  transitionConversation,
} from "./conversationCoordinator";

const turns = [
  { id: "system-1", speaker: "system", text: "第一句" },
  { id: "student-1", speaker: "student", text: "回應第一句" },
  { id: "system-2", speaker: "system", text: "第二句" },
  { id: "student-2", speaker: "student", text: "回應第二句" },
] as const;

describe("conversation coordinator", () => {
  it("uses null as the legacy fallback for missing or invalid conversations", () => {
    expect(createConversationState(undefined)).toBeNull();
    expect(createConversationState([{ id: "scene", speaker: "system", text: "only one" }])).toBeNull();
  });

  it("starts on a system turn and does not analyze it", () => {
    const state = createConversationState(turns);

    expect(state).toEqual({ turnIndex: 0, step: "system" });
    expect(currentConversationTurn(state!, turns)?.id).toBe("system-1");
    expect(isStudentRecordingStep(state!)).toBe(false);
    expect(shouldAnalyzeConversationTurn(state!)).toBe(false);
  });

  it("requires the system turn to complete before opening recording", () => {
    const initial = createConversationState(turns)!;
    const blocked = transitionConversation(
      initial,
      { type: "studentRecordingCompleted", recordingId: "audio-1" },
      turns,
    );
    const advanced = transitionConversation(initial, { type: "systemAudioCompleted" }, turns);

    expect(blocked).toEqual({ state: initial, accepted: false });
    expect(advanced).toEqual({ state: { turnIndex: 1, step: "student" }, accepted: true });
    expect(shouldAnalyzeConversationTurn(advanced.state)).toBe(true);
  });

  it("requires a recording before self-evaluation and keeps its identity", () => {
    const student = transitionConversation(
      createConversationState(turns)!,
      { type: "systemAudioCompleted" },
      turns,
    ).state;
    const blocked = transitionConversation(student, { type: "selfEvaluationSubmitted" }, turns);
    const accepted = transitionConversation(
      student,
      { type: "studentRecordingCompleted", recordingId: "audio-1" },
      turns,
    );

    expect(blocked).toEqual({ state: student, accepted: false });
    expect(accepted).toEqual({
      state: { turnIndex: 1, step: "selfEval", studentRecordingId: "audio-1" },
      accepted: true,
    });
  });

  it("alternates system and student turns, then ends at summary", () => {
    let state = transitionConversation(
      createConversationState(turns)!,
      { type: "systemAudioCompleted" },
      turns,
    ).state;
    state = transitionConversation(state, { type: "studentRecordingCompleted", recordingId: "audio-1" }, turns).state;
    state = transitionConversation(state, { type: "selfEvaluationSkipped" }, turns).state;
    state = transitionConversation(state, { type: "feedbackCompleted" }, turns).state;
    expect(state).toEqual({ turnIndex: 2, step: "system" });
    expect(currentConversationTurn(state, turns)?.speaker).toBe("system");

    state = transitionConversation(state, { type: "systemAudioCompleted" }, turns).state;
    state = transitionConversation(state, { type: "studentRecordingCompleted", recordingId: "audio-2" }, turns).state;
    state = transitionConversation(state, { type: "selfEvaluationSubmitted" }, turns).state;
    state = transitionConversation(state, { type: "feedbackCompleted" }, turns).state;

    expect(state).toEqual({ turnIndex: 4, step: "summary" });
    expect(currentConversationTurn(state, turns)).toBeNull();
    expect(transitionConversation(state, { type: "systemAudioCompleted" }, turns)).toEqual({
      state,
      accepted: false,
    });
  });
});
