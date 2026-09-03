import type { SelfEvalLevel } from "../utils/selfEvalComparison";
import StudentIcon, { type StudentIconName } from "./StudentIcon";

const LEVEL_ICON: Record<SelfEvalLevel, StudentIconName> = {
  good: "face-good",
  ok: "face-neutral",
  bad: "face-hard",
};

/** Calm, non-emoji self-rating mark shared by student and teacher views. */
export default function SelfEvalIcon({ level, size = 24 }: { level: SelfEvalLevel; size?: number }) {
  return <StudentIcon name={LEVEL_ICON[level]} size={size} aria-hidden="true" />;
}
