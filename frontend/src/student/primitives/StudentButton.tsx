import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import StudentIcon from "./StudentIcon";
import "./StudentButton.css";

export type StudentButtonVariant = "primary" | "secondary" | "subtle" | "danger";
export type StudentButtonSize = "sm" | "default" | "lg";

interface StudentButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: StudentButtonVariant;
  size?: StudentButtonSize;
  icon?: string;
  iconTrailing?: string;
  children: ReactNode;
}

/**
 * The only four button variants for Student Mode (DESIGN.md). Default height
 * is 44px (a real touch target, not the 34px in the mockup's dense desktop
 * chrome) — "sm" is for dense inline row actions only, never a page's
 * primary action.
 */
const StudentButton = forwardRef<HTMLButtonElement, StudentButtonProps>(
  ({ variant = "secondary", size = "default", icon, iconTrailing, children, className = "", ...rest }, ref) => {
    return (
      <button
        ref={ref}
        type="button"
        className={`sa-button sa-button--${variant} sa-button--${size} ${className}`.trim()}
        {...rest}
      >
        {icon && <StudentIcon name={icon} size={size === "sm" ? 16 : 18} role="decorative" />}
        <span className="sa-button__label">{children}</span>
        {iconTrailing && <StudentIcon name={iconTrailing} size={size === "sm" ? 16 : 18} role="decorative" />}
      </button>
    );
  },
);
StudentButton.displayName = "StudentButton";

export default StudentButton;
