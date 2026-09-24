import type { HTMLAttributes, ReactNode } from "react";
import "./StudentSection.css";

export type StudentSectionVariant = "flat" | "panel" | "tinted";

interface StudentSectionProps extends HTMLAttributes<HTMLDivElement> {
  variant?: StudentSectionVariant;
  children: ReactNode;
}

/** The one card/panel wrapper. "flat" = no border, no fill (grouping only).
 * "panel" = surface-container-lowest + 1px border, the workhorse card.
 * "tinted" = a soft container-low fill, no border (secondary emphasis). */
export default function StudentSection({ variant = "panel", className = "", children, ...rest }: StudentSectionProps) {
  return (
    <div className={`sa-section sa-section--${variant} ${className}`.trim()} {...rest}>
      {children}
    </div>
  );
}
