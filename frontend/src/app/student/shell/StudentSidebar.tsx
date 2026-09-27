import StudentIcon from "@shared/ui/student/StudentIcon";
import StudentSystemText from "@shared/ui/student/StudentSystemText";
import "./StudentSidebar.css";

export type StudentTopSection = "study" | "progress" | "placement";
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
  /** The active topic has no teacher-authored conversationTurns — hide the
   */
  /** Conversation is always visible in the lesson phase navigation. */
  quizStars?: number;
  maxQuizStars?: number;
  /** The furthest phase this lesson attempt has actually reached — phases
   * beyond it are locked (defaults to `activePhase`, so a sidebar rendered
   * without this prop only ever treats the phase it's currently showing as
   * reached, never unlocking ahead of it). */
  furthestPhase?: StudentPhase | null;
  /** Whether the vocab-quiz 3★ gate has been cleared for the active topic —
   * gates the "story-speaking" item specifically, independent of the
   * furthest-phase watermark (defaults to true so callers that omit it see
   * unchanged behavior). */
  speakingUnlocked?: boolean;
  conversationUnlocked?: boolean;
  /** Allows either practice to be selected directly after the quiz gate. */
  practiceChoicesUnlocked?: boolean;
  currentLessonTitle?: string;
  onNavigateSection: (section: StudentTopSection) => void;
  onNavigatePhase?: (phase: StudentPhase) => void;
  onLogout: () => void;
}

export default function StudentSidebar({
  studentName,
  activeSection,
  activePhase,
  quizStars = 0,
  maxQuizStars = 0,
  furthestPhase,
  speakingUnlocked = true,
  conversationUnlocked = false,
  practiceChoicesUnlocked = false,
  currentLessonTitle,
  onNavigateSection,
  onNavigatePhase,
  onLogout,
}: StudentSidebarProps) {
  const furthestIndex = PHASE_ORDER.indexOf(
    furthestPhase ?? activePhase ?? PHASE_ORDER[0],
  );
  const quizReached = furthestIndex >= PHASE_ORDER.indexOf("vocab-quiz");

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
            {PHASE_NAV.map((phase) => {
              const starLocked =
                phase.id === "story-speaking" && !speakingUnlocked;
              const practiceOpen =
                quizReached &&
                practiceChoicesUnlocked &&
                (phase.id === "story-speaking"
                  ? speakingUnlocked
                  : phase.id === "conversation" && conversationUnlocked);
              const locked =
                (!practiceOpen &&
                  PHASE_ORDER.indexOf(phase.id) > furthestIndex) ||
                starLocked;
              return (
                <button
                  key={phase.id}
                  type="button"
                  className={`sa-sidebar__phase-item ${activePhase === phase.id ? "is-active" : ""} ${locked ? "is-locked" : ""}`}
                  aria-current={activePhase === phase.id ? "page" : undefined}
                  disabled={locked}
                  aria-label={locked ? (starLocked ? "完成三星後解鎖" : "請先完成前一個步驟") : undefined}
                  onClick={() => onNavigatePhase(phase.id)}
                >
                  {locked ? (
                    <StudentIcon name="lock" size={14} role="decorative" />
                  ) : (
                    <span
                      className="sa-sidebar__phase-dot"
                      aria-hidden="true"
                    />
                  )}
                  <StudentSystemText k={PHASE_COPY[phase.id]} withinControl />
                </button>
              );
            })}
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
