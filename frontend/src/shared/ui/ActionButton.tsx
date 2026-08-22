import type { ButtonHTMLAttributes, PropsWithChildren } from "react";

export interface ActionButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary";
}

/** Shared action primitive for the staged frontend migration. */
export default function ActionButton({
  variant = "secondary",
  className = "",
  children,
  ...props
}: PropsWithChildren<ActionButtonProps>) {
  return (
    <button
      {...props}
      className={`workspace-${variant}-action ${className}`.trim()}
    >
      {children}
    </button>
  );
}
