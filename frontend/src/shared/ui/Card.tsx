import type { HTMLAttributes, PropsWithChildren } from "react";

export interface CardProps extends HTMLAttributes<HTMLElement> {
  as?: "article" | "div" | "section";
  tone?: "default" | "soft" | "accent";
}

/** Shared surface primitive. Product-specific layouts can add their own class. */
export default function Card({
  as = "div",
  tone = "default",
  className = "",
  children,
  ...props
}: PropsWithChildren<CardProps>) {
  const Component = as;
  return (
    <Component
      {...props}
      className={`ui-card ui-card-${tone} ${className}`.trim()}
    >
      {children}
    </Component>
  );
}
