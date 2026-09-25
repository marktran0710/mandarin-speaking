import { getStudentScopeKey } from "../../utils/studentSession";

export type StudyPhaseKey = "vocab" | "quiz" | "speaking" | "conversation";
export type StudyPhaseFlags = Record<StudyPhaseKey, boolean>;

const FLAG_KEY_PREFIX = "studentPhaseFlags:";
const EMPTY_FLAGS: StudyPhaseFlags = { vocab: false, quiz: false, speaking: false, conversation: false };

function flagKey(topicId: string): string {
  return `${FLAG_KEY_PREFIX}${getStudentScopeKey()}:${topicId}`;
}

export function loadPhaseFlags(topicId: string): StudyPhaseFlags {
  try {
    const raw = sessionStorage.getItem(flagKey(topicId));
    if (!raw) return { ...EMPTY_FLAGS };
    return { ...EMPTY_FLAGS, ...JSON.parse(raw) };
  } catch {
    return { ...EMPTY_FLAGS };
  }
}

export function markPhaseSeen(topicId: string, phase: StudyPhaseKey): void {
  try {
    const current = loadPhaseFlags(topicId);
    current[phase] = true;
    sessionStorage.setItem(flagKey(topicId), JSON.stringify(current));
  } catch {
    /* storage unavailable; the phase strip simply stays unchanged */
  }
}
