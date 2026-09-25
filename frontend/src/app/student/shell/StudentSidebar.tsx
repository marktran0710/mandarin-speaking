import StudentIcon from "@shared/ui/student/StudentIcon";
import "./StudentSidebar.css";

export type StudentTopSection = "study" | "progress" | "placement";
export type StudentPhase = "vocab-preview" | "vocab-quiz" | "story-speaking" | "conversation" | "submit" | "completion";

const PHASE_NAV: Array<{ id: StudentPhase; labelZh: string; labelEn: string }> = [
  { id: "vocab-preview", labelZh: "生詞預習", labelEn: "Vocab Preview" },
  { id: "vocab-quiz", labelZh: "詞彙練習", labelEn: "Vocab Quiz" },
  { id: "story-speaking", labelZh: "口語練習", labelEn: "Story Speaking" },
  { id: "conversation", labelZh: "對話練習", labelEn: "Conversation" },
  { id: "submit", labelZh: "提交", labelEn: "Submit" },
];

/** "completion" has no nav button but is a real reachable StudentPhase —
 * appended so watermark comparisons below never miss it. */
export const PHASE_ORDER: StudentPhase[] = [...PHASE_NAV.map((phase) => phase.id), "completion"];

interface StudentSidebarProps {
  studentName: string;
  activeSection: StudentTopSection;
  activePhase?: StudentPhase | null;
  /** The active topic has no teacher-authored conversationTurns — hide the
   * Conversation phase nav item rather than linking to a dead completion
   * stub (StudentApp falls back to that stub when this phase has nothing
   * to render). */
  hasConversation?: boolean;
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
  onNavigateSection: (section: StudentTopSection) => void;
  onNavigatePhase?: (phase: StudentPhase) => void;
  onLogout: () => void;
}

export default function StudentSidebar({
  studentName,
  activeSection,
  activePhase,
  hasConversation = true,
  quizStars = 0,
  maxQuizStars = 0,
  furthestPhase,
  speakingUnlocked = true,
  conversationUnlocked = false,
  practiceChoicesUnlocked = false,
  onNavigateSection,
  onNavigatePhase,
  onLogout,
}: StudentSidebarProps) {
  const visiblePhaseNav = PHASE_NAV.filter((phase) => phase.id !== "conversation" || hasConversation);
  const furthestIndex = PHASE_ORDER.indexOf(furthestPhase ?? activePhase ?? PHASE_ORDER[0]);

  return (
    <aside className="sa-sidebar">
      <div className="sa-sidebar__top">
        <div className="sa-sidebar__brand">
          <span className="sa-sidebar__brand-mark" lang="zh-Hant">慢</span>
          <span className="sa-sidebar__brand-name" lang="zh-Hant">慢慢中文</span>
        </div>

        <nav className="sa-sidebar__nav" aria-label="Learning areas">
          <button
            type="button"
            className={`sa-sidebar__nav-item ${activeSection === "study" ? "is-active" : ""}`}
            aria-current={activeSection === "study" ? "page" : undefined}
            onClick={() => onNavigateSection("study")}
          >
            <span className="sa-sidebar__nav-item-main">
              <StudentIcon name="menu_book" size={18} role="decorative" />
              <span><span lang="zh-Hant">課程</span> · Lessons</span>
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
              <span><span lang="zh-Hant">進度</span> · Progress</span>
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
              <span><span lang="zh-Hant">入門測驗</span> · Placement</span>
            </span>
          </button>
        </nav>

        {maxQuizStars > 0 && (
          <section className="sa-sidebar__stars" aria-label="Learning stars">
            <div className="sa-sidebar__stars-head">
              <span className="sa-sidebar__stars-label">
                <StudentIcon name="star" size={18} role="decorative" filled />
                <span lang="zh-Hant">星星</span> · Stars
              </span>
              <span><strong>{quizStars}</strong> / {maxQuizStars}</span>
            </div>
            <div className="sa-sidebar__stars-track" aria-hidden="true">
              <span style={{ width: `${(quizStars / maxQuizStars) * 100}%` }} />
            </div>
          </section>
        )}

        {activeSection === "study" && activePhase && onNavigatePhase && (
          <nav className="sa-sidebar__nav sa-sidebar__phase-nav" aria-label="Lesson phase">
            <p className="sa-sidebar__nav-label"><span lang="zh-Hant">課程階段</span> · Pedagogical Phase</p>
            {visiblePhaseNav.map((phase) => {
              const starLocked = phase.id === "story-speaking" && !speakingUnlocked;
              const practiceOpen = practiceChoicesUnlocked && (phase.id === "story-speaking"
                ? speakingUnlocked
                : phase.id === "conversation" && conversationUnlocked);
              const locked = (!practiceOpen && PHASE_ORDER.indexOf(phase.id) > furthestIndex) || starLocked;
              return (
                <button
                  key={phase.id}
                  type="button"
                  className={`sa-sidebar__phase-item ${activePhase === phase.id ? "is-active" : ""} ${locked ? "is-locked" : ""}`}
                  aria-current={activePhase === phase.id ? "page" : undefined}
                  disabled={locked}
                  title={locked ? (starLocked ? "Earn 3⭐ to unlock" : "Complete the previous step first") : undefined}
                  onClick={() => onNavigatePhase(phase.id)}
                >
                  {locked ? (
                    <StudentIcon name="lock" size={14} role="decorative" />
                  ) : (
                    <span className="sa-sidebar__phase-dot" aria-hidden="true" />
                  )}
                  <span><span lang="zh-Hant">{phase.labelZh}</span> · {phase.labelEn}</span>
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
          <span className="sa-sidebar__identity-name">{studentName || "Learner"}</span>
        </div>
        <button type="button" className="sa-sidebar__footer-action" onClick={onLogout}>
          <span className="sa-sidebar__footer-action-label">
            <StudentIcon name="logout" size={18} role="decorative" />
            <span lang="zh-Hant">登出</span> · Log out
          </span>
        </button>
        <p className="sa-sidebar__legal">NTNU 《時代華語一》 · Educational Use</p>
      </div>
    </aside>
  );
}
