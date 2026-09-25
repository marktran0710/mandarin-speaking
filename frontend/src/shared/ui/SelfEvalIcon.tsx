import type { SelfEvalLevel } from "../../utils/selfEvalComparison";
import Icon, { type UiIconName } from "./Icon";

const LEVEL_ICON: Record<SelfEvalLevel, UiIconName> = {
  good: "face-good",
  ok: "face-neutral",
  bad: "face-hard",
};

/** Calm, non-emoji self-rating mark shared by student and teacher views. */
export default function SelfEvalIcon({ level, size = 24 }: { level: SelfEvalLevel; size?: number }) {
  return <Icon name={LEVEL_ICON[level]} size={size} aria-hidden="true" />;
}
