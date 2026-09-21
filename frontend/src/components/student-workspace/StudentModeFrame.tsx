import { useEffect, useRef, type ReactNode } from "react";
import StudentSidebar from "./StudentSidebar";
import type { StudentIconName } from "../navigation/StudentIcon";
import type { WorkspaceView } from "../../types/studentWorkspace";
import "./StudentModeCompact.css";

export const STUDENT_WORKSPACE_VIEWS: Array<{
  id: WorkspaceView;
  icon: StudentIconName;
  label: { zh: string; pinyin: string; en: string };
}> = [
  {
    // zh/en must agree with every other place these two phrases appear
    // (TopicSelector's "課程完成 / Lessons complete", Navigation's and
    // MyStoriesPage's "我的學習 / My learning") — a bilingual learner reading
    // 課程 as "Practice" here and "Lessons" one screen later, for the exact
    // same characters, undermines the vocabulary the app is teaching them.
    id: "practice",
    icon: "image",
    label: { zh: "課程", pinyin: "Kèchéng", en: "Lessons" },
  },
  {
    id: "progress",
    icon: "chart",
    label: { zh: "我的學習", pinyin: "Wǒ de xuéxí", en: "My learning" },
  },
];

interface StudentModeFrameProps {
  activeView: WorkspaceView | null;
  onChange: (view: WorkspaceView) => void;
  studentName: string;
  onLogout: () => void;
  totalStars: number;
  maxStars: number;
  children: ReactNode;
  ariaLabel?: string;
  className?: string;
  /** Resets the workspace panel when its view or activity boundary changes. */
  panelScrollKey?: string | number;
  onOpenPlacementTest?: () => void;
  placementTestActive?: boolean;
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
  panelScrollKey,
  onOpenPlacementTest,
  placementTestActive,
}: StudentModeFrameProps) {
  const panelRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (panelRef.current) panelRef.current.scrollTop = 0;
  }, [panelScrollKey]);

  return (
    <>
      <a className="student-skip-link" href="#student-workspace-panel">Skip to learning content</a>
      <div className={`student-workspace student-workspace-v2 ${className}`.trim()}>
        <StudentSidebar
          views={STUDENT_WORKSPACE_VIEWS}
          activeView={activeView}
          onChange={onChange}
          studentName={studentName}
          onLogout={onLogout}
          totalStars={totalStars}
          maxStars={maxStars}
          onOpenPlacementTest={onOpenPlacementTest}
          placementTestActive={placementTestActive}
        />
        <main
          id="student-workspace-panel"
          ref={panelRef}
          className="student-workspace-content student-workspace-content-v2"
          tabIndex={-1}
          aria-label={ariaLabel}
          aria-live="polite"
        >
          {children}
        </main>
      </div>
    </>
  );
}
