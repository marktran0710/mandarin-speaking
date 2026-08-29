import { useState } from "react";
import StudentIcon, { type StudentIconName } from "../StudentIcon";
import { BiLabel, type BiLabelProps } from "../BiLabel";
import ToneMark from "../ToneMark";
import useColorMode from "../../hooks/useColorMode";
import type { WorkspaceView } from "../../types/studentWorkspace";
import "./StudentSidebar.css";

interface StudentSidebarProps {
  views: Array<{ id: WorkspaceView; icon: StudentIconName; label: BiLabelProps }>;
  activeView: WorkspaceView;
  onChange: (view: WorkspaceView) => void;
  studentName: string;
  onLogout: () => void;
  /** Quiz stars earned across every story that has a quiz, and the
   * ceiling (3 per story). Rendered as the rail's progress card, which
   * replaced the floating star bubble that used to sit over the
   * bottom-right corner of every page. */
  totalStars: number;
  maxStars: number;
}

/** The student shell's single navigation surface.
 *
 * It replaces three stacked rows that all said the same thing: the top
 * navbar's "我的學習" link, a page-sized "我的學習" heading, and a
 * "我的學習 / 課程" tab pair directly under it. One rail now carries the
 * section switch, identity, and account actions, matching the left sidebar
 * the teacher shell (ManagementShell) already uses.
 *
 * It is deliberately NOT rendered during a practice session — StoryRecorder
 * brings its own left rail (StorySessionSidebar), and two left rails side by
 * side is the stacking problem this redesign exists to remove.
 */
export default function StudentSidebar({
  views,
  activeView,
  onChange,
  studentName,
  onLogout,
  totalStars,
  maxStars,
}: StudentSidebarProps) {
  const [colorMode, toggleColorMode] = useColorMode();
  const [drawerOpen, setDrawerOpen] = useState(false);

  // Roving tabindex + arrow keys, carried over from the tab bar this
  // replaces: the rail is one tab stop, arrows move within it. Up/Down are
  // the primary axis now that the list is vertical; Left/Right still work so
  // muscle memory from the old horizontal tabs keeps working.
  const handleKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (!views.length || !["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"].includes(event.key)) {
      return;
    }
    event.preventDefault();
    const currentIndex = Math.max(0, views.findIndex((view) => view.id === activeView));
    const direction = event.key === "ArrowDown" || event.key === "ArrowRight" ? 1 : -1;
    const nextIndex = (currentIndex + direction + views.length) % views.length;
    onChange(views[nextIndex].id);
    document.getElementById(`student-nav-${views[nextIndex].id}`)?.focus();
  };

  const select = (view: WorkspaceView) => {
    onChange(view);
    setDrawerOpen(false);
  };

  return (
    <>
      <button
        type="button"
        className="student-sidebar-toggle"
        aria-label={drawerOpen ? "Close menu" : "Open menu"}
        aria-expanded={drawerOpen}
        aria-controls="student-sidebar"
        onClick={() => setDrawerOpen((open) => !open)}
      >
        <StudentIcon name={drawerOpen ? "close" : "menu"} size={20} />
      </button>

      {drawerOpen && (
        <div
          className="student-sidebar-backdrop"
          aria-hidden="true"
          onClick={() => setDrawerOpen(false)}
        />
      )}

      <aside
        id="student-sidebar"
        className={`student-sidebar${drawerOpen ? " is-open" : ""}`}
      >
        <div className="student-sidebar-brand">
          <img src="/logo.png" alt="" aria-hidden="true" />
          <span className="student-sidebar-brand-name" lang="zh-Hant">慢慢中文</span>
          <ToneMark className="student-sidebar-tonemark" size={22} />
        </div>

        <nav className="student-sidebar-nav" aria-label="Learning areas">
          {views.map((item) => {
            const isActive = activeView === item.id;
            return (
              <button
                key={item.id}
                id={`student-nav-${item.id}`}
                type="button"
                aria-current={isActive ? "page" : undefined}
                tabIndex={isActive ? 0 : -1}
                className={`student-sidebar-item${isActive ? " active" : ""}`}
                onClick={() => select(item.id)}
                onKeyDown={handleKeyDown}
              >
                <span className="student-sidebar-item-icon">
                  <StudentIcon name={item.icon} size={20} />
                </span>
                <span className="student-sidebar-item-copy">
                  <BiLabel {...item.label} />
                </span>
              </button>
            );
          })}
        </nav>

        {/* Sits with the account block at the bottom, not under the nav:
            stars are "how I'm doing", which belongs beside "who I am"
            rather than in the middle of the section switch. */}
        <div className="student-sidebar-footer">
        {maxStars > 0 && (
          <div className="student-sidebar-progress">
            <p className="student-sidebar-progress-label">
              <StudentIcon name="star" size={15} />
              <BiLabel zh="星星" pinyin="Xīngxing" en="Stars" />
            </p>
            <p className="student-sidebar-progress-value">
              {totalStars}
              <span> / {maxStars}</span>
            </p>
            <div
              className="student-sidebar-progress-track"
              role="progressbar"
              aria-valuenow={totalStars}
              aria-valuemin={0}
              aria-valuemax={maxStars}
              aria-label="Quiz stars earned"
            >
              <span style={{ width: `${Math.round((totalStars / maxStars) * 100)}%` }} />
            </div>
          </div>
        )}

          <div className="student-sidebar-identity">
            <span className="student-sidebar-avatar" aria-hidden="true">
              <StudentIcon name="user" size={17} />
            </span>
            <span className="student-sidebar-identity-copy">
              <span className="student-sidebar-identity-label">
                <span lang="zh-Hant">學生帳號</span>
                <span aria-hidden="true"> · </span>
                <span>Username</span>
              </span>
              <strong className="student-sidebar-identity-name">{studentName}</strong>
            </span>
          </div>

          <button
            type="button"
            className="student-sidebar-action"
            onClick={toggleColorMode}
            aria-pressed={colorMode === "dark"}
          >
            <StudentIcon name={colorMode === "dark" ? "sun" : "moon"} size={17} />
            {colorMode === "dark" ? (
              <BiLabel zh="亮色" pinyin="Liàngsè" en="Light" />
            ) : (
              <BiLabel zh="深色" pinyin="Shēnsè" en="Dark" />
            )}
          </button>

          <button
            type="button"
            className="student-sidebar-action student-sidebar-logout"
            onClick={onLogout}
          >
            <StudentIcon name="logout" size={17} />
            <BiLabel k="log_out" />
          </button>
        </div>
      </aside>
    </>
  );
}
