import StudentIcon, { type StudentIconName } from "../StudentIcon";
import { BiLabel, type BiLabelProps } from "../BiLabel";
import type { WorkspaceView } from "../../types/studentWorkspace";

interface WorkspaceAreaTabsProps {
  views: Array<{
    id: WorkspaceView;
    icon: StudentIconName;
    label: BiLabelProps;
  }>;
  activeView: WorkspaceView;
  onChange: (view: WorkspaceView) => void;
}

export default function WorkspaceAreaTabs({ views, activeView, onChange }: WorkspaceAreaTabsProps) {
  const handleKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (!views.length || !["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"].includes(event.key)) {
      return;
    }
    event.preventDefault();
    const currentIndex = Math.max(0, views.findIndex((view) => view.id === activeView));
    const direction = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : -1;
    const nextIndex = (currentIndex + direction + views.length) % views.length;
    onChange(views[nextIndex].id);
    document.getElementById(`student-workspace-tab-${views[nextIndex].id}`)?.focus();
  };

  return (
    <nav
      className={`student-workspace-tabs student-workspace-tabs-count-${views.length}`}
      aria-label="Student learning areas"
      role="tablist"
    >
      {views.map((item) => (
        <button
          key={item.id}
          id={`student-workspace-tab-${item.id}`}
          type="button"
          role="tab"
          aria-selected={activeView === item.id}
          aria-controls="student-workspace-panel"
          tabIndex={activeView === item.id ? 0 : -1}
          className={`student-workspace-tab ${activeView === item.id ? "active" : ""}`}
          onClick={() => onChange(item.id)}
          onKeyDown={handleKeyDown}
        >
          <span className="student-workspace-tab-icon">
            <StudentIcon name={item.icon} size={23} />
          </span>
          <span className="student-workspace-tab-copy">
            <BiLabel {...item.label} />
          </span>
          <StudentIcon name="arrow-right" size={16} className="student-workspace-tab-arrow" aria-hidden="true" />
        </button>
      ))}
    </nav>
  );
}
