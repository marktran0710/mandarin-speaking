import type { HTMLAttributes, ReactNode } from "react";
import "./StudentLayoutPrimitives.css";

export type StudentLayoutDensity = "tight" | "compact" | "comfortable" | "section";
export type StudentGridColumns = 2 | 3 | 4;
export type StudentPageBodyVariant = "flow" | "task" | "stage";
export type StudentActionAlignment = "start" | "center" | "end" | "between";

type StudentLayoutProps = HTMLAttributes<HTMLDivElement> & {
  children: ReactNode;
  density?: StudentLayoutDensity;
};

/** The one page-owned child inside StudentPageShell's rail. */
export function StudentPageBody({
  children,
  variant = "flow",
  className = "",
  ...props
}: HTMLAttributes<HTMLDivElement> & {
  children: ReactNode;
  variant?: StudentPageBodyVariant;
}) {
  return (
    <div
      {...props}
      className={`student-page-body student-page-body--${variant}${className ? ` ${className}` : ""}`}
      data-student-body={variant}
    >
      {children}
    </div>
  );
}

/** A vertical rhythm primitive. Parent-owned gap prevents child margin drift. */
export function StudentStack({
  children,
  density = "comfortable",
  className = "",
  ...props
}: StudentLayoutProps) {
  return (
    <div
      {...props}
      className={`student-stack student-stack--${density}${className ? ` ${className}` : ""}`}
    >
      {children}
    </div>
  );
}

/** A wrapping horizontal group for related controls, labels, or status chips. */
export function StudentCluster({
  children,
  density = "compact",
  className = "",
  ...props
}: StudentLayoutProps) {
  return (
    <div
      {...props}
      className={`student-cluster student-cluster--${density}${className ? ` ${className}` : ""}`}
    >
      {children}
    </div>
  );
}

/** A responsive equal-track grid for repeated items at the same hierarchy. */
export function StudentGrid({
  children,
  columns = 2,
  density = "comfortable",
  className = "",
  ...props
}: StudentLayoutProps & { columns?: StudentGridColumns }) {
  return (
    <div
      {...props}
      className={`student-grid student-grid--${columns} student-grid--${density}${className ? ` ${className}` : ""}`}
    >
      {children}
    </div>
  );
}

/** A single row anatomy: leading content, flexible body, optional trailing content. */
export function StudentRow({
  children,
  density = "comfortable",
  className = "",
  ...props
}: StudentLayoutProps) {
  return (
    <div
      {...props}
      className={`student-row student-row--${density}${className ? ` ${className}` : ""}`}
    >
      {children}
    </div>
  );
}

/** One action group per context; wraps naturally on narrow screens. */
export function StudentActionBar({
  children,
  density = "compact",
  align = "end",
  className = "",
  ...props
}: StudentLayoutProps & { align?: StudentActionAlignment }) {
  return (
    <div
      {...props}
      className={`student-action-bar student-action-bar--${density} student-action-bar--${align}${className ? ` ${className}` : ""}`}
    >
      {children}
    </div>
  );
}
