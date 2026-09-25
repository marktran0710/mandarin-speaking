import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import "./Button.css";

export type ButtonTone = "primary" | "secondary" | "subtle" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  tone?: ButtonTone;
  size?: ButtonSize;
  children: ReactNode;
}

/** Canonical product button. Role-specific surfaces select tokens via CSS/theme, not a duplicate component. */
const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button({
  tone = "primary",
  size = "md",
  className = "",
  type = "button",
  children,
  ...props
}, ref) {
  return (
    <button ref={ref} {...props} type={type} className={`ui-button ui-button-${tone} ui-button-${size} ${className}`.trim()}>
      {children}
    </button>
  );
});

export default Button;
