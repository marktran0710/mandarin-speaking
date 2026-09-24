import StudentIcon from "./StudentIcon";
import "./StudentStatusPill.css";

export type StudentStatusTone = "success" | "info" | "selected" | "attention" | "danger" | "neutral";

interface StudentStatusPillProps {
  tone: StudentStatusTone;
  icon?: string;
  children: React.ReactNode;
}

const ICON_BY_TONE: Record<StudentStatusTone, string | undefined> = {
  success: "check",
  info: "play_circle",
  selected: "adjust",
  attention: "change_history",
  danger: "error",
  neutral: "lock",
};

/**
 * Non-interactive status badge. Never color-only: every tone pairs with an
 * icon (or the caller's own icon) plus the visible text label.
 */
export default function StudentStatusPill({ tone, icon, children }: StudentStatusPillProps) {
  const resolvedIcon = icon ?? ICON_BY_TONE[tone];
  return (
    <span className={`sa-status-pill sa-status-pill--${tone}`} role="status">
      {resolvedIcon && <StudentIcon name={resolvedIcon} size={14} role="decorative" />}
      {children}
    </span>
  );
}
