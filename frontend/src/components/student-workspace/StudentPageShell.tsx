import type { HTMLAttributes, ReactNode } from "react";
import "./StudentPageShell.css";

export type StudentPageShellLayout = "content" | "task" | "stage";
export type StudentPageShellVariant = "catalogue" | "progress" | "quiz" | "activity";
/** The only page templates allowed inside StudentModeFrame. */
export type StudentPageTemplate = "catalogue" | "dashboard" | "activity" | "assessment";

type StudentPageShellProps = HTMLAttributes<HTMLDivElement> & {
  children: ReactNode;
  /** Canonical page template. New student pages should use this prop. */
  template?: StudentPageTemplate;
  /** Compatibility alias for pages that have not migrated yet. */
  layout?: StudentPageShellLayout;
  /** Compatibility alias for pages that have not migrated yet. */
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
  template,
  variant,
  layout,
  pageId,
  ...props
}: StudentPageShellProps) {
  const resolvedTemplate: StudentPageTemplate =
    template ??
    (variant === "quiz"
      ? "assessment"
      : variant === "activity"
        ? "activity"
        : variant === "progress"
          ? "dashboard"
          : "catalogue");
  const resolvedLayout: StudentPageShellLayout =
    layout ?? (resolvedTemplate === "assessment" ? "task" : resolvedTemplate === "activity" ? "stage" : "content");
  const compatibilityClasses = [
    `student-page-shell--${resolvedLayout}`,
    variant ? `student-page-shell--${variant}` : "",
  ].filter(Boolean).join(" ");

  return (
    <div
      {...props}
      className={`student-page-shell student-page-shell--${resolvedTemplate} ${compatibilityClasses}${className ? ` ${className}` : ""}`}
      data-student-page={pageId}
      data-student-template={resolvedTemplate}
    >
      <div className="student-page-shell__rail">{children}</div>
    </div>
  );
}
