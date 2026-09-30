import type { StudentUiCopyKey } from "../../i18n/student-ui-copy";
import type { SceneSubmission } from "../../services/database";
import type { StudentPhase } from "./shell/StudentSidebar";

export type LessonNavPhase = Exclude<StudentPhase, "completion">;

/** Everything the lesson step gates are derived from. Every field comes from
 * saved data (quiz attempts, speaking records, submission status, the saved
 * "preview finished" flag) — never from where the learner happened to click
 * in this browser tab — so reopening a lesson or refreshing the page shows
 * the same locks as before. */
export interface LessonProgressInput {
  hasQuiz: boolean;
  previewDone: boolean;
  /** All three quiz rounds finished at least once (score is not a gate). */
  quizDone: boolean;
  sceneCount: number;
  scenesRecorded: number;
  turnCount: number;
  turnsRecorded: number;
  conversationAvailable: boolean;
  submitted: boolean;
}

export interface LessonStepState {
  visible: boolean;
  unlocked: boolean;
  done: boolean;
  /** Why the step is locked, shown when the learner clicks it anyway. */
  lockReason?: StudentUiCopyKey;
}

export type LessonSteps = Record<LessonNavPhase, LessonStepState>;

export function speakingPathDone(input: Pick<LessonProgressInput, "sceneCount" | "scenesRecorded">): boolean {
  return input.sceneCount > 0 && input.scenesRecorded >= input.sceneCount;
}

export function conversationPathDone(input: Pick<LessonProgressInput, "turnCount" | "turnsRecorded">): boolean {
  return input.turnCount > 0 && input.turnsRecorded >= input.turnCount;
}

export function computeLessonSteps(input: LessonProgressInput): LessonSteps {
  const speakingDone = speakingPathDone(input);
  const conversationDone = conversationPathDone(input);
  const anyRecording = input.scenesRecorded > 0 || input.turnsRecorded > 0;
  // Quiz or recording evidence cannot replace the explicit vocabulary preview.
  // The preview is the learner's first exposure and remains a real gate.
  const previewDone = input.submitted || input.previewDone || anyRecording;
  const practiceOpen = input.submitted || (previewDone && (!input.hasQuiz || input.quizDone));
  const practiceLockReason: StudentUiCopyKey = input.hasQuiz ? "lockedUntilQuizRounds" : "lockedUntilPreview";

  return {
    "vocab-preview": { visible: true, unlocked: true, done: previewDone },
    "vocab-quiz": {
      visible: input.hasQuiz,
      unlocked: previewDone,
      done: input.quizDone,
      lockReason: previewDone ? undefined : "lockedUntilPreview",
    },
    "story-speaking": {
      visible: true,
      unlocked: practiceOpen,
      done: speakingDone,
      lockReason: practiceOpen ? undefined : practiceLockReason,
    },
    conversation: {
      visible: true,
      unlocked: practiceOpen && input.conversationAvailable,
      done: conversationDone,
      lockReason: !input.conversationAvailable
        ? "lockedNoConversation"
        : practiceOpen ? undefined : practiceLockReason,
    },
    submit: {
      visible: true,
      unlocked: input.submitted || speakingDone || conversationDone,
      done: input.submitted,
      lockReason: input.submitted || speakingDone || conversationDone ? undefined : "lockedUntilPracticePath",
    },
  };
}

/** Where a reopened lesson should land: the first step with work left. */
export function firstUnfinishedPhase(input: LessonProgressInput): LessonNavPhase {
  const steps = computeLessonSteps(input);
  if (input.submitted) return "vocab-preview";
  if (!steps["vocab-preview"].done) return "vocab-preview";
  if (steps["vocab-quiz"].visible && !steps["vocab-quiz"].done) return "vocab-quiz";
  // Submit unlocks as soon as ONE practice path is finished, but that must not
  // trap a learner who is still mid-way through the other path: keep landing
  // them on the half-done path and leave Submit to the sidebar/path CTAs.
  const speakingInProgress = input.sceneCount > 0 && input.scenesRecorded > 0 && !speakingPathDone(input);
  const conversationInProgress =
    input.conversationAvailable && input.turnCount > 0 && input.turnsRecorded > 0 && !conversationPathDone(input);
  if (steps.submit.unlocked) {
    if (speakingInProgress) return "story-speaking";
    if (conversationInProgress) return "conversation";
    return "submit";
  }
  // Nothing finished yet: resume whichever practice path the learner already started.
  const conversationProgress = input.turnCount > 0 ? input.turnsRecorded / input.turnCount : 0;
  const speakingProgress = input.sceneCount > 0 ? input.scenesRecorded / input.sceneCount : 0;
  return steps.conversation.unlocked && conversationProgress > speakingProgress ? "conversation" : "story-speaking";
}

interface SavedSpeakingRow {
  sceneIndex: number;
  turnId?: string | null;
  turnIndex?: number | null;
  latestResult?: SceneSubmission | null;
  updatedAt?: string;
}

/** Rebuild the in-memory `speaking:<scene>` / `conversation:<turn>` map from
 * the server's saved speaking progress, so a refresh or a reopened lesson
 * keeps every recorded scene/turn (and therefore its unlocks and its place
 * in the final submission). Later saves win when a turn was redone in a new
 * conversation session. */
export function sceneSubmissionsFromProgress(rows: SavedSpeakingRow[]): Record<string, SceneSubmission> {
  const ordered = [...rows].sort((a, b) => String(a.updatedAt ?? "").localeCompare(String(b.updatedAt ?? "")));
  const restored: Record<string, SceneSubmission> = {};
  for (const row of ordered) {
    if (!row.latestResult) continue;
    const isConversation = Boolean(row.turnId) || typeof row.turnIndex === "number";
    if (isConversation) {
      if (typeof row.turnIndex !== "number") continue;
      restored[`conversation:${row.turnIndex}`] = row.latestResult;
    } else {
      restored[`speaking:${row.sceneIndex}`] = row.latestResult;
    }
  }
  return restored;
}

export function countRecorded(
  submissions: Record<string, SceneSubmission>,
  prefix: "speaking" | "conversation",
  indexes: number[],
): number {
  return indexes.filter((index) => Boolean(submissions[`${prefix}:${index}`])).length;
}

/** The scenes to hand in: every scene/turn of a finished path. A path the
 * learner only half-did is left out, per the "submit finished work" rule. */
export function scenesForSubmission(
  submissions: Record<string, SceneSubmission>,
  paths: { speaking: boolean; conversation: boolean },
): SceneSubmission[] {
  return Object.entries(submissions)
    .filter(([key]) => (key.startsWith("speaking:") ? paths.speaking : key.startsWith("conversation:") ? paths.conversation : false))
    .sort(([a], [b]) => a.localeCompare(b, undefined, { numeric: true }))
    .map(([, submission]) => submission);
}
