import StudentIcon from "../primitives/StudentIcon";
import "./StudentSidebar.css";

export type StudentTopSection = "study" | "progress";
export type StudentPhase = "vocab-preview" | "vocab-quiz" | "story-speaking" | "conversation" | "completion";

const PHASE_NAV: Array<{ id: StudentPhase; label: string }> = [
  { id: "vocab-preview", label: "Vocab Preview" },
  { id: "vocab-quiz", label: "Vocab Quiz" },
  { id: "story-speaking", label: "Story Speaking" },
  { id: "conversation", label: "Conversation" },
];

interface StudentSidebarProps {
  studentName: string;
  activeSection: StudentTopSection;
  activePhase?: StudentPhase | null;
  onNavigateSection: (section: StudentTopSection) => void;
  onNavigatePhase?: (phase: StudentPhase) => void;
  onLogout: () => void;
}

export default function StudentSidebar({
  studentName,
  activeSection,
  activePhase,
  onNavigateSection,
  onNavigatePhase,
  onLogout,
}: StudentSidebarProps) {
  return (
    <aside className="sa-sidebar">
      <div className="sa-sidebar__top">
        <div className="sa-sidebar__brand">
          <span className="sa-sidebar__brand-name" lang="zh-Hant">慢慢中文</span>
          <span className="sa-sidebar__research-badge">RESEARCH</span>
        </div>

        <nav className="sa-sidebar__nav" aria-label="Sections">
          <p className="sa-sidebar__nav-label">Curriculum Core</p>
          <button
            type="button"
            className={`sa-sidebar__nav-item ${activeSection === "study" ? "is-active" : ""}`}
            aria-current={activeSection === "study" ? "page" : undefined}
            onClick={() => onNavigateSection("study")}
          >
            <span className="sa-sidebar__nav-item-main">
              <StudentIcon name="menu_book" size={18} role="decorative" />
              Study
            </span>
            <span lang="zh-Hant" className="sa-sidebar__nav-item-hanzi">研讀</span>
          </button>
          <button
            type="button"
            className={`sa-sidebar__nav-item ${activeSection === "progress" ? "is-active" : ""}`}
            aria-current={activeSection === "progress" ? "page" : undefined}
            onClick={() => onNavigateSection("progress")}
          >
            <span className="sa-sidebar__nav-item-main">
              <StudentIcon name="analytics" size={18} role="decorative" />
              Progress
            </span>
            <span lang="zh-Hant" className="sa-sidebar__nav-item-hanzi">進度</span>
          </button>
        </nav>

        {activeSection === "study" && activePhase && onNavigatePhase && (
          <nav className="sa-sidebar__nav" aria-label="Lesson phase">
            <p className="sa-sidebar__nav-label">Pedagogical Phase</p>
            {PHASE_NAV.map((phase) => (
              <button
                key={phase.id}
                type="button"
                className={`sa-sidebar__phase-item ${activePhase === phase.id ? "is-active" : ""}`}
                aria-current={activePhase === phase.id ? "page" : undefined}
                onClick={() => onNavigatePhase(phase.id)}
              >
                <span className="sa-sidebar__phase-dot" aria-hidden="true" />
                {phase.label}
              </button>
            ))}
          </nav>
        )}
      </div>

      <div className="sa-sidebar__footer">
        <div className="sa-sidebar__session">
          <span className="sa-sidebar__session-dot" aria-hidden="true" />
          <span>Session Active</span>
        </div>
        <div className="sa-sidebar__identity">
          <span className="sa-sidebar__identity-name">{studentName}</span>
          <button
            type="button"
            className="sa-sidebar__logout"
            onClick={onLogout}
            title="End session"
          >
            <StudentIcon name="logout" size={18} role="meaningful" label="Log out" />
          </button>
        </div>
      </div>
    </aside>
  );
}
