import { useEffect, useState } from "react";
import StudentIcon from "@shared/ui/student/StudentIcon";
import StudentSystemText from "@shared/ui/student/StudentSystemText";
import type { StudentUiCopyKey } from "../../../i18n/student-ui-copy";
import type { LessonNavPhase, LessonStepState, LessonSteps } from "../lessonSteps";
import "./StudentSidebar.css";

export type StudentTopSection = "study" | "progress" | "placement" | "settings";
export type StudentPhase =
  | "vocab-preview"
  | "vocab-quiz"
  | "story-speaking"
  | "conversation"
  | "submit"
  | "completion";

const PHASE_NAV: Array<{ id: Exclude<StudentPhase, "completion"> }> =
  [
    { id: "vocab-preview" },
    { id: "vocab-quiz" },
    { id: "story-speaking" },
    { id: "conversation" },
    { id: "submit" },
  ];

const PHASE_COPY = {
  "vocab-preview": "vocabPreview",
  "vocab-quiz": "vocabQuiz",
  "story-speaking": "storySpeaking",
  conversation: "conversation",
  submit: "submit",
} as const;

/** Story speaking and conversation are equivalent paths — the learner picks
 * one, so the sidebar groups them under a "choose one" label. */
const PRACTICE_PATHS: LessonNavPhase[] = ["story-speaking", "conversation"];

/** "completion" has no nav button but is a real reachable StudentPhase —
 * appended so watermark comparisons below never miss it. */
export const PHASE_ORDER: StudentPhase[] = [
  ...PHASE_NAV.map((phase) => phase.id),
  "completion",
];

interface StudentSidebarProps {
  studentName: string;
  activeSection: StudentTopSection;
  activePhase?: StudentPhase | null;
  quizStars?: number;
  maxQuizStars?: number;
  /** Per-step gate state for the open lesson, derived from saved progress
   * (see app/student/lessonSteps.ts). Omitted → every step is open. */
  steps?: LessonSteps;
  currentLessonTitle?: string;
  onNavigateSection: (section: StudentTopSection) => void;
  onNavigatePhase?: (phase: StudentPhase) => void;
  onLogout: () => void;
}

const OPEN_STEP: LessonStepState = { visible: true, unlocked: true, done: false };

export default function StudentSidebar({
  studentName,
  activeSection,
  activePhase,
  quizStars = 0,
  maxQuizStars = 0,
  steps,
  currentLessonTitle,
  onNavigateSection,
  onNavigatePhase,
  onLogout,
}: StudentSidebarProps) {
  const [lockNotice, setLockNotice] = useState<{ phase: StudentPhase; reason: StudentUiCopyKey } | null>(null);

  useEffect(() => {
    setLockNotice(null);
  }, [activePhase]);

  const renderPhase = (phase: { id: LessonNavPhase }) => {
    const step = steps?.[phase.id] ?? OPEN_STEP;
    if (!step.visible) return null;
    const locked = !step.unlocked;
    const noticeId = `sa-phase-lock-${phase.id}`;
    const showNotice = locked && lockNotice?.phase === phase.id;
    return (
      <div key={phase.id} className="sa-sidebar__phase-row">
        <button
          type="button"
          className={`sa-sidebar__phase-item ${activePhase === phase.id ? "is-active" : ""} ${locked ? "is-locked" : ""} ${step.done ? "is-done" : ""}`}
          aria-current={activePhase === phase.id ? "page" : undefined}
          aria-disabled={locked || undefined}
          aria-describedby={showNotice ? noticeId : undefined}
          data-phase={phase.id}
          onClick={() => {
            if (locked) {
              setLockNotice(step.lockReason ? { phase: phase.id, reason: step.lockReason } : null);
              return;
            }
            setLockNotice(null);
            onNavigatePhase?.(phase.id);
          }}
        >
          {locked ? (
            <StudentIcon name="lock" size={14} role="decorative" />
          ) : step.done ? (
            <StudentIcon name="check_circle" size={14} role="decorative" filled />
          ) : (
            <span className="sa-sidebar__phase-dot" aria-hidden="true" />
          )}
          <StudentSystemText k={PHASE_COPY[phase.id]} withinControl />
          {step.done && <span className="sa-sidebar__sr-only" lang="zh-Hant">（已完成）</span>}
        </button>
        {showNotice && lockNotice && (
          <p id={noticeId} className="sa-sidebar__lock-notice" role="status">
            <StudentSystemText k={lockNotice.reason} />
          </p>
        )}
      </div>
    );
  };

  return (
    <aside className="sa-sidebar">
      <div className="sa-sidebar__top">
        <div className="sa-sidebar__brand">
          <span className="sa-sidebar__brand-mark" lang="zh-Hant">
            慢
          </span>
          <span className="sa-sidebar__brand-name" lang="zh-Hant">
            慢慢中文
          </span>
        </div>

        <nav className="sa-sidebar__nav" aria-label="學習區域">
          <button
            type="button"
            className={`sa-sidebar__nav-item ${activeSection === "study" ? "is-active" : ""}`}
            aria-current={activeSection === "study" ? "page" : undefined}
            onClick={() => onNavigateSection("study")}
          >
            <span className="sa-sidebar__nav-item-main">
              <StudentIcon name="menu_book" size={18} role="decorative" />
              <span>
                <StudentSystemText k="lessons" withinControl />
              </span>
            </span>
          </button>
          <button
            type="button"
            className={`sa-sidebar__nav-item ${activeSection === "progress" ? "is-active" : ""}`}
            aria-current={activeSection === "progress" ? "page" : undefined}
            onClick={() => onNavigateSection("progress")}
          >
            <span className="sa-sidebar__nav-item-main">
              <StudentIcon name="trending_up" size={18} role="decorative" />
              <span>
                <StudentSystemText k="progress" withinControl />
              </span>
            </span>
          </button>
          <button
            type="button"
            className={`sa-sidebar__nav-item ${activeSection === "placement" ? "is-active" : ""}`}
            aria-current={activeSection === "placement" ? "page" : undefined}
            onClick={() => onNavigateSection("placement")}
          >
            <span className="sa-sidebar__nav-item-main">
              <StudentIcon name="flag" size={18} role="decorative" />
              <span>
                <StudentSystemText k="placement" withinControl />
              </span>
            </span>
          </button>
          <button
            type="button"
            className={`sa-sidebar__nav-item ${activeSection === "settings" ? "is-active" : ""}`}
            aria-current={activeSection === "settings" ? "page" : undefined}
            onClick={() => onNavigateSection("settings")}
          >
            <span className="sa-sidebar__nav-item-main">
              <StudentIcon name="settings" size={18} role="decorative" />
              <span>
                <StudentSystemText k="settings" withinControl />
              </span>
            </span>
          </button>
        </nav>

        {activeSection === "study" && maxQuizStars > 0 && (
          <section className="sa-sidebar__stars" aria-label="學習星星">
            <div className="sa-sidebar__stars-head">
              <span className="sa-sidebar__stars-label">
                <StudentIcon name="star" size={18} role="decorative" filled />
                <StudentSystemText k="stars" withinControl />
              </span>
              <span>
                <strong>{quizStars}</strong> / {maxQuizStars}
              </span>
            </div>
            <div className="sa-sidebar__stars-track" aria-hidden="true">
              <span style={{ width: `${(quizStars / maxQuizStars) * 100}%` }} />
            </div>
          </section>
        )}

        {activeSection === "study" && currentLessonTitle && (
          <div className="sa-sidebar__current-lesson">
            <span className="sa-sidebar__current-lesson-label"><StudentSystemText k="currentLesson" /></span>
            <strong lang="zh-Hant">{currentLessonTitle}</strong>
          </div>
        )}

        {activeSection === "study" && activePhase && onNavigatePhase && (
          <nav
            className="sa-sidebar__nav sa-sidebar__phase-nav"
            aria-label="課程階段"
          >
            <p className="sa-sidebar__nav-label">
              <StudentSystemText k="lessonPhase" />
            </p>
            {PHASE_NAV.filter((phase) => !PRACTICE_PATHS.includes(phase.id) && phase.id !== "submit").map(renderPhase)}
            <div className="sa-sidebar__phase-group" role="group" aria-labelledby="sa-phase-choose-one">
              <p id="sa-phase-choose-one" className="sa-sidebar__phase-group-label">
                <StudentSystemText k="chooseOne" />
              </p>
              {PHASE_NAV.filter((phase) => PRACTICE_PATHS.includes(phase.id)).map(renderPhase)}
            </div>
            {PHASE_NAV.filter((phase) => phase.id === "submit").map(renderPhase)}
          </nav>
        )}
      </div>

      <div className="sa-sidebar__footer">
        <div className="sa-sidebar__identity">
          <span className="sa-sidebar__identity-avatar" aria-hidden="true">
            <StudentIcon name="person" size={17} role="decorative" />
          </span>
          <span className="sa-sidebar__identity-name">
            {studentName || <StudentSystemText k="learner" withinControl />}
          </span>
        </div>
        <button
          type="button"
          className="sa-sidebar__footer-action"
          onClick={onLogout}
        >
          <span className="sa-sidebar__footer-action-label">
            <StudentIcon name="logout" size={18} role="decorative" />
            <StudentSystemText k="logout" withinControl />
          </span>
        </button>
        <p className="sa-sidebar__legal">
          NTNU 《時代華語一》 · 僅供教學使用
        </p>
      </div>
    </aside>
  );
}
