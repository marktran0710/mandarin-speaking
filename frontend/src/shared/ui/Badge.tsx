import type { HTMLAttributes, PropsWithChildren } from "react";

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: "neutral" | "jade" | "amber" | "error";
}

export default function Badge({
  tone = "neutral",
  className = "",
  children,
  ...props
}: PropsWithChildren<BadgeProps>) {
  return (
    <span {...props} className={`ui-badge ui-badge-${tone} ${className}`.trim()}>
      {children}
    </span>
  );
}
