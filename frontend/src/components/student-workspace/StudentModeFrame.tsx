import type { ReactNode } from "react";
import StudentSidebar from "./StudentSidebar";
import type { StudentIconName } from "../StudentIcon";
import type { WorkspaceView } from "../../types/studentWorkspace";

export const STUDENT_WORKSPACE_VIEWS: Array<{
  id: WorkspaceView;
  icon: StudentIconName;
  label: { zh: string; pinyin: string; en: string };
}> = [
  {
    id: "practice",
    icon: "image",
    label: { zh: "課程", pinyin: "Kèchéng", en: "Practice" },
  },
  {
    id: "progress",
    icon: "chart",
    label: { zh: "我的學習", pinyin: "Wǒ de xuéxí", en: "Progress" },
  },
];

interface StudentModeFrameProps {
  activeView: WorkspaceView;
  onChange: (view: WorkspaceView) => void;
  studentName: string;
  onLogout: () => void;
  totalStars: number;
  maxStars: number;
  children: ReactNode;
  ariaLabel?: string;
  className?: string;
}

/** Shared student shell for both workspace views and standalone student tools. */
export default function StudentModeFrame({
  activeView,
  onChange,
  studentName,
  onLogout,
  totalStars,
  maxStars,
  children,
  ariaLabel,
  className = "",
}: StudentModeFrameProps) {
  return (
    <main className={`student-workspace student-workspace-v2 ${className}`.trim()}>
      <StudentSidebar
        views={STUDENT_WORKSPACE_VIEWS}
        activeView={activeView}
        onChange={onChange}
        studentName={studentName}
        onLogout={onLogout}
        totalStars={totalStars}
        maxStars={maxStars}
      />
      <section
        id="student-workspace-panel"
        className="student-workspace-content student-workspace-content-v2"
        tabIndex={-1}
        aria-label={ariaLabel}
        aria-live="polite"
      >
        {children}
      </section>
    </main>
  );
}
