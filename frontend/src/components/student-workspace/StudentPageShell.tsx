import type { HTMLAttributes, ReactNode } from "react";
import "./StudentPageShell.css";

export type StudentPageShellLayout = "content" | "task" | "stage";
export type StudentPageShellVariant = "catalogue" | "progress" | "quiz" | "activity";

type StudentPageShellProps = HTMLAttributes<HTMLDivElement> & {
  children: ReactNode;
  /** New semantic layout contract. */
  layout?: StudentPageShellLayout;
  /** Legacy page variant kept as a compatibility alias during migration. */
  variant?: StudentPageShellVariant;
  /** Stable page identity for layout QA and future analytics hooks. */
  pageId?: string;
};

/**
 * One direct child for student pages inside StudentModeFrame's content panel.
 * It standardizes the page boundary without taking over navigation or scroll.
 */
export default function StudentPageShell({
  children,
  className = "",
  variant,
  layout,
  pageId,
  ...props
}: StudentPageShellProps) {
  const resolvedLayout: StudentPageShellLayout =
    layout ?? (variant === "quiz" ? "task" : variant === "activity" ? "stage" : "content");
  const legacyVariantClass = variant ? ` student-page-shell--${variant}` : "";

  return (
    <div
      {...props}
      className={`student-page-shell student-page-shell--${resolvedLayout}${legacyVariantClass}${className ? ` ${className}` : ""}`}
      data-student-page={pageId}
    >
      <div className="student-page-shell__rail">{children}</div>
    </div>
  );
}
