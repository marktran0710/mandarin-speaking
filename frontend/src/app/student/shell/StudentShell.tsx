import { useState, type ReactNode } from "react";
import StudentSidebar, {
  type StudentPhase,
  type StudentTopSection,
} from "./StudentSidebar";
import StudentIcon from "@shared/ui/student/StudentIcon";
import StudentSystemText from "@shared/ui/student/StudentSystemText";
import "./StudentShell.css";

interface StudentShellProps {
  studentName: string;
  activeSection: StudentTopSection;
  activePhase?: StudentPhase | null;
  quizStars?: number;
  maxQuizStars?: number;
  furthestPhase?: StudentPhase | null;
  practiceChoicesUnlocked?: boolean;
  vocabularyPracticeUnlocked?: boolean;
  currentLessonTitle?: string;
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
  quizStars,
  maxQuizStars,
  furthestPhase,
  practiceChoicesUnlocked,
  vocabularyPracticeUnlocked,
  currentLessonTitle,
  onNavigateSection,
  onNavigatePhase,
  onLogout,
  children,
}: StudentShellProps) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="student-app sa-shell">
      <a href="#sa-main" className="sa-skip-link">
        <StudentSystemText k="skipToContent" withinControl />
      </a>

      <div className={`sa-shell__sidebar-wrap ${mobileOpen ? "is-open" : ""}`}>
        <StudentSidebar
          studentName={studentName}
          activeSection={activeSection}
          activePhase={activePhase}
          quizStars={quizStars}
          maxQuizStars={maxQuizStars}
          furthestPhase={furthestPhase}
          practiceChoicesUnlocked={practiceChoicesUnlocked}
          vocabularyPracticeUnlocked={vocabularyPracticeUnlocked}
          currentLessonTitle={currentLessonTitle}
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
          aria-label="關閉選單"
          onClick={() => setMobileOpen(false)}
        />
      )}

      <header className="sa-shell__mobile-bar">
        <button
          type="button"
          className="sa-shell__menu-btn"
          onClick={() => setMobileOpen(true)}
          aria-label="開啟選單"
        >
          <StudentIcon
            name="menu"
            size={22}
            role="meaningful"
            label="開啟選單"
          />
        </button>
        <StudentSystemText k="brand" className="sa-shell__mobile-brand" />
      </header>

      <main id="sa-main" className="sa-shell__main" tabIndex={-1}>
        {children}
      </main>
    </div>
  );
}
