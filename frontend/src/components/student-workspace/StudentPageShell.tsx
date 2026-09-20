import type { HTMLAttributes, ReactNode } from "react";
import "./StudentPageShell.css";

export type StudentPageShellVariant = "catalogue" | "progress" | "quiz";

type StudentPageShellProps = HTMLAttributes<HTMLDivElement> & {
  children: ReactNode;
  /** Selects page spacing only; StudentModeFrame remains the outer surface/scroller. */
  variant: StudentPageShellVariant;
};

/**
 * One direct child for student pages inside StudentModeFrame's content panel.
 * It standardizes the page boundary without taking over navigation or scroll.
 */
export default function StudentPageShell({
  children,
  className = "",
  variant,
  ...props
}: StudentPageShellProps) {
  return (
    <div
      {...props}
      className={`student-page-shell student-page-shell--${variant} ${className}`.trim()}
    >
      {children}
    </div>
  );
}
