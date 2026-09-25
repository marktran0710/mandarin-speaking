import { useState, type ReactNode } from "react";
import StudentSidebar, { type StudentPhase, type StudentTopSection } from "./StudentSidebar";
import StudentIcon from "../primitives/StudentIcon";
import "./StudentShell.css";

interface StudentShellProps {
  studentName: string;
  activeSection: StudentTopSection;
  activePhase?: StudentPhase | null;
  hasConversation?: boolean;
  quizStars?: number;
  maxQuizStars?: number;
  furthestPhase?: StudentPhase | null;
  speakingUnlocked?: boolean;
  onNavigateSection: (section: StudentTopSection) => void;
  onNavigatePhase?: (phase: StudentPhase) => void;
  onLogout: () => void;
  children: ReactNode;
}

/**
 * Owns only: sidebar, main content area, gutters, main scroll, mobile
 * drawer toggle. Knows nothing about quiz/speaking/conversation/feedback
 * state — every page below it owns that.
 */
export default function StudentShell({
  studentName,
  activeSection,
  activePhase,
  hasConversation,
  quizStars,
  maxQuizStars,
  furthestPhase,
  speakingUnlocked,
  onNavigateSection,
  onNavigatePhase,
  onLogout,
  children,
}: StudentShellProps) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="student-app sa-shell">
      <a href="#sa-main" className="sa-skip-link">Skip to learning content</a>

      <div className={`sa-shell__sidebar-wrap ${mobileOpen ? "is-open" : ""}`}>
        <StudentSidebar
          studentName={studentName}
          activeSection={activeSection}
          activePhase={activePhase}
          hasConversation={hasConversation}
          quizStars={quizStars}
          maxQuizStars={maxQuizStars}
          furthestPhase={furthestPhase}
          speakingUnlocked={speakingUnlocked}
          onNavigateSection={(section) => {
            onNavigateSection(section);
            setMobileOpen(false);
          }}
          onNavigatePhase={
            onNavigatePhase &&
            ((phase) => {
              onNavigatePhase(phase);
              setMobileOpen(false);
            })
          }
          onLogout={onLogout}
        />
      </div>
      {mobileOpen && (
        <button
          type="button"
          className="sa-shell__backdrop"
          aria-label="Close menu"
          onClick={() => setMobileOpen(false)}
        />
      )}

      <header className="sa-shell__mobile-bar">
        <button
          type="button"
          className="sa-shell__menu-btn"
          onClick={() => setMobileOpen(true)}
          aria-label="Open menu"
        >
          <StudentIcon name="menu" size={22} role="meaningful" label="Open menu" />
        </button>
        <span className="sa-shell__mobile-brand" lang="zh-Hant">慢慢中文</span>
      </header>

      <main id="sa-main" className="sa-shell__main" tabIndex={-1}>
        {children}
      </main>
    </div>
  );
}
