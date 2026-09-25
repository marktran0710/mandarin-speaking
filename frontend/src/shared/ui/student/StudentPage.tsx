import type { ReactNode } from "react";
import StudentIcon from "./StudentIcon";
import StudentSection from "./StudentSection";
import "./layout.css";
import "./StudentPage.css";

export type StudentPageLayout = "hub" | "task" | "stage";
export type StudentPageState = "loading" | "empty" | "error" | "ready";

export interface StudentPageActions {
  /** The one primary action for this state — always rendered on the right. */
  primary: ReactNode;
  secondary?: ReactNode;
}

interface StudentPageProps {
  layout: StudentPageLayout;
  /** A <StudentPageHeader ... /> element — every screen gets exactly one H1
   * this way (HEAD-1). */
  header: ReactNode;
  state?: StudentPageState;
  /** Only used when state is "empty". */
  emptyTitle?: ReactNode;
  emptyText?: ReactNode;
  emptyAction?: ReactNode;
  /** Only used when state is "error"; falls back to a generic message. */
  errorText?: ReactNode;
  /** hub: secondary (rail) column. stage: media/image column. Unused by task. */
  rail?: ReactNode;
  media?: ReactNode;
  /** task only: content that legitimately needs more than 720px (e.g. the
   * quiz workspace's question + stats rail) opts out of the narrow column
   * rather than being forced into it. */
  wide?: boolean;
  actions?: StudentPageActions;
  children?: ReactNode;
  className?: string;
}

/**
 * The one page shell for Student Mode (LAYOUT-1). Three layouts share the
 * same header, content-left-edge, and footer action bar so no screen rolls
 * its own frame — see AGENT_RULES.md "Student Mode page rules".
 */
export default function StudentPage({
  layout,
  header,
  state = "ready",
  emptyTitle,
  emptyText,
  emptyAction,
  errorText,
  rail,
  media,
  wide = false,
  actions,
  children,
  className = "",
}: StudentPageProps) {
  return (
    <div className={`sa-page-container sa-page sa-page--${layout} ${wide ? "sa-page--wide" : ""} ${className}`.trim()}>
      {header}

      <div className="sa-page__body">
        {state === "loading" && (
          <p className="sa-page__status" role="status">
            <span lang="zh-Hant">載入中</span> · Loading…
          </p>
        )}

        {state === "error" && (
          <StudentSection variant="panel" className="sa-page__state-card">
            <StudentIcon name="error" size={22} role="decorative" />
            <p>{errorText ?? <><span lang="zh-Hant">發生錯誤</span> · Something went wrong.</>}</p>
          </StudentSection>
        )}

        {state === "empty" && (
          <StudentSection variant="panel" className="sa-page__state-card">
            <StudentIcon name="inbox" size={22} role="decorative" />
            {emptyTitle && <h2>{emptyTitle}</h2>}
            {emptyText && <p>{emptyText}</p>}
            {emptyAction}
          </StudentSection>
        )}

        {state === "ready" && layout === "hub" && (
          <div className={`sa-page__hub-grid ${rail ? "" : "sa-page__hub-grid--single"}`.trim()}>
            <div className="sa-page__hub-main">{children}</div>
            {rail && <aside className="sa-page__hub-rail">{rail}</aside>}
          </div>
        )}

        {state === "ready" && layout === "task" && (
          <div className="sa-page__task">{children}</div>
        )}

        {state === "ready" && layout === "stage" && (
          <div className={`sa-page__stage-split ${media ? "" : "sa-page__stage-split--single"}`.trim()}>
            {media && <div className="sa-page__stage-media">{media}</div>}
            <div className="sa-page__stage-activity">{children}</div>
          </div>
        )}
      </div>

      {state === "ready" && actions && (
        <div className="sa-page__actions">
          {actions.secondary && <div className="sa-page__actions-secondary">{actions.secondary}</div>}
          {actions.primary}
        </div>
      )}
    </div>
  );
}
