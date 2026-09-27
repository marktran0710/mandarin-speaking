import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import Button from "../Button";
import StudentIcon from "./StudentIcon";
import { collectStudentSystemTextHints, StudentControlTooltipContext } from "./StudentSystemText";
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
 * chrome) ??"sm" is for dense inline row actions only, never a page's
 * primary action.
 */
const StudentButton = forwardRef<HTMLButtonElement, StudentButtonProps>(
  ({ variant = "secondary", size = "default", icon, iconTrailing, children, className = "", ...rest }, ref) => {
    const hints = collectStudentSystemTextHints(children);
    const pinyin = hints.map((hint) => hint.pinyin).join(" ");
    const english = hints.map((hint) => hint.english).filter((value): value is string => Boolean(value)).join(" · ");
    return (
      <Button
        ref={ref}
        {...rest}
        type="button"
        tone={variant}
        size={size === "default" ? "md" : size}
        className={`sa-button sa-button--${variant} sa-button--${size} ${className}`.trim()}
      >
        {icon && <StudentIcon name={icon} size={size === "sm" ? 16 : 18} role="decorative" />}
        <StudentControlTooltipContext.Provider value>
          <span className="sa-button__label">{children}</span>
        </StudentControlTooltipContext.Provider>
        {hints.length > 0 && (
          <span className="sa-button__tooltip" role="tooltip" aria-hidden="true">
            <span className="sa-button__tooltip-pinyin">{pinyin}</span>
            {english && <small className="sa-button__tooltip-en" lang="en">{english}</small>}
          </span>
        )}
        {iconTrailing && <StudentIcon name={iconTrailing} size={size === "sm" ? 16 : 18} role="decorative" />}
      </Button>
    );
  },
);
StudentButton.displayName = "StudentButton";

export default StudentButton;
