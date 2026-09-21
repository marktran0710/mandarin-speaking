import type { HTMLAttributes, ReactNode } from "react";
import "./StudentSection.css";

export type StudentSectionVariant = "plain" | "surface" | "soft" | "task";
export type StudentSectionBodyLayout = "stack" | "grid" | "split" | "task";
export type StudentSectionDensity = "comfortable" | "compact";

type StudentSectionProps = HTMLAttributes<HTMLElement> & {
  variant?: StudentSectionVariant;
  density?: StudentSectionDensity;
  children: ReactNode;
};

export function StudentSection({
  variant = "plain",
  density = "comfortable",
  className = "",
  children,
  ...props
}: StudentSectionProps) {
  return (
    <section
      className={`student-section student-section--${variant} student-section--density-${density} ${className}`.trim()}
      {...props}
    >
      {children}
    </section>
  );
}

type StudentSectionHeaderProps = {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  headingLevel?: 1 | 2 | 3 | 4 | 5 | 6;
  headingId?: string;
  className?: string;
};

export function StudentSectionHeader({
  title,
  description,
  action,
  headingLevel = 2,
  headingId,
  className = "",
}: StudentSectionHeaderProps) {
  const Heading = `h${headingLevel}` as keyof JSX.IntrinsicElements;

  return (
    <header className={`student-section__header ${className}`.trim()}>
      <div className="student-section__header-copy">
        <Heading id={headingId} className="student-section__title">
          {title}
        </Heading>
        {description && <div className="student-section__description">{description}</div>}
      </div>
      {action && <div className="student-section__header-action">{action}</div>}
    </header>
  );
}

type StudentSectionBodyProps = HTMLAttributes<HTMLDivElement> & {
  layout?: StudentSectionBodyLayout;
  children: ReactNode;
};

export function StudentSectionBody({
  layout = "stack",
  className = "",
  children,
  ...props
}: StudentSectionBodyProps) {
  return (
    <div
      className={`student-section__body student-section__body--${layout} ${className}`.trim()}
      {...props}
    >
      {children}
    </div>
  );
}

type StudentSectionFooterProps = HTMLAttributes<HTMLElement> & {
  align?: "start" | "center" | "end";
  children: ReactNode;
};

export function StudentSectionFooter({
  align = "end",
  className = "",
  children,
  ...props
}: StudentSectionFooterProps) {
  return (
    <footer
      className={`student-section__footer student-section__footer--${align} ${className}`.trim()}
      {...props}
    >
      {children}
    </footer>
  );
}
