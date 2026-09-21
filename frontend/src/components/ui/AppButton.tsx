import type { ButtonHTMLAttributes, ReactNode } from "react";
import "./AppButton.css";

export type AppButtonTone = "primary" | "secondary" | "subtle" | "danger";
export type AppButtonSize = "sm" | "md" | "lg";

/**
 * Shared button primitive for the application. It keeps action hierarchy,
 * keyboard focus, disabled states, and sizing consistent while letting a
 * page add a small layout-specific class when it genuinely needs one.
 */
export default function AppButton({
  tone = "primary",
  size = "md",
  className = "",
  type = "button",
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  tone?: AppButtonTone;
  size?: AppButtonSize;
  children: ReactNode;
}) {
  return (
    <button
      {...props}
      type={type}
      className={`ui-button ui-button-${tone} ui-button-${size} ${className}`.trim()}
    >
      {children}
    </button>
  );
}
