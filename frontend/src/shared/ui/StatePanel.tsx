import type { ReactNode } from "react";

export type StatePanelKind = "empty" | "loading" | "error";

export interface StatePanelProps {
  kind: StatePanelKind;
  title: string;
  description?: string;
  action?: ReactNode;
}

const ICONS: Record<StatePanelKind, string> = {
  empty: "○",
  loading: "…",
  error: "!",
};

export default function StatePanel({ kind, title, description, action }: StatePanelProps) {
  return (
    <section className={`ui-state-panel ui-state-panel-${kind}`} role={kind === "error" ? "alert" : undefined}>
      <span className="ui-state-panel-icon" aria-hidden="true">{ICONS[kind]}</span>
      <div>
        <h2>{title}</h2>
        {description && <p>{description}</p>}
        {action && <div className="ui-state-panel-action">{action}</div>}
      </div>
    </section>
  );
}
