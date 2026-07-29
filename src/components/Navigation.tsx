import "./Navigation.css";
import { Page } from "../types/page";
import { LoginRole } from "../pages/LoginPage";
import { BiLabel } from "./BiLabel";
import ToneMark from "./ToneMark";
import useColorMode from "../hooks/useColorMode";
import "./BiLabel.css";

interface NavigationProps {
  currentPage: Page;
  activeRole: LoginRole | null;
  onNavigate: (page: Page) => void;
  onLogout: () => void;
  /** Shrinks the navbar to just the logo + log out, hiding the section
   * tabs — used while a student is mid-practice-session so this bar isn't
   * one more stacked nav row above the story's own back/progress panel. */
  compact?: boolean;
  /** The student app (index.html) and teacher app (teacher.html) are two
   * separate Vite entries sharing this component — this picks which
   * pre-login nav items and logo target make sense for each. Neither
   * variant links to the other: the two modes are deliberately reachable
   * only by typing their own URL (see WrongMode). */
  appVariant?: "student" | "teacher";
  /** Whether the class has any published story in the matching narrative
   * mode. These two sections are hidden rather than shown empty, since most
   * classes only publish plain "story" mode — but they must be linked once
   * content exists, or a teacher's describe / listen_retell stories have no
   * student-facing entry point at all (they were unreachable until now). */
  hasDescribeStories?: boolean;
  hasListenRetellStories?: boolean;
}

export default function Navigation({
  currentPage,
  activeRole,
  onNavigate,
  onLogout,
  compact = false,
  appVariant = "student",
  hasDescribeStories = false,
  hasListenRetellStories = false,
}: NavigationProps) {
  const [colorMode, toggleColorMode] = useColorMode();
  const isStudent = activeRole === "student";
  // The teacher app renders this bar only on its login screen (once logged
  // in, TeacherShell's own topbar takes over), so the teacher logo has just
  // one target — there is no in-app dashboard page to route to.
  const logoTarget: Page = appVariant === "teacher" ? "teacher-login" : "home";

  return (
    <nav className="navbar">
      <div className="navbar-container">
        <button
          type="button"
          className="navbar-logo"
          onClick={() => onNavigate(logoTarget)}
        >
          <img className="logo-icon" src="/logo.png" alt="慢慢中文 logo" />
          <span>慢慢中文</span>
          <ToneMark className="navbar-tonemark" size={26} />
        </button>

        <ul className="navbar-menu">
          {!compact && !activeRole && appVariant === "student" && (
            <>
              <li>
                <button
                  type="button"
                  className={`nav-link ${currentPage === "home" ? "active" : ""}`}
                  onClick={() => onNavigate("home")}
                >
                  <BiLabel k="portals" />
                </button>
              </li>
              <li>
                <button
                  type="button"
                  className={`nav-link ${currentPage === "student-login" ? "active" : ""}`}
                  onClick={() => onNavigate("student-login")}
                >
                  <BiLabel k="student_login" />
                </button>
              </li>
            </>
          )}

          {!compact && isStudent && (
            <>
              <li>
                <button
                  type="button"
                  className={`nav-link ${currentPage === "student-practice" ? "active" : ""}`}
                  onClick={() => onNavigate("student-practice")}
                >
                  <BiLabel k="training" />
                </button>
              </li>
              <li>
                <button
                  type="button"
                  className={`nav-link ${currentPage === "tone-practice" ? "active" : ""}`}
                  onClick={() => onNavigate("tone-practice")}
                >
                  <BiLabel zh="聲調練習" pinyin="Shēngdiào liànxí" en="Tone practice" />
                </button>
              </li>
              <li>
                <button
                  type="button"
                  className={`nav-link ${currentPage === "student-stories" ? "active" : ""}`}
                  onClick={() => onNavigate("student-stories")}
                >
                  <BiLabel zh="我的成績" pinyin="Wǒ de chéngjì" en="My Profile" />
                </button>
              </li>
              {hasDescribeStories && (
                <li>
                  <button
                    type="button"
                    className={`nav-link ${currentPage === "image-narration" ? "active" : ""}`}
                    onClick={() => onNavigate("image-narration")}
                  >
                    <BiLabel zh="看圖說話" pinyin="Kàn tú shuō huà" en="Picture talk" />
                  </button>
                </li>
              )}
              {hasListenRetellStories && (
                <li>
                  <button
                    type="button"
                    className={`nav-link ${currentPage === "listen-retell" ? "active" : ""}`}
                    onClick={() => onNavigate("listen-retell")}
                  >
                    <BiLabel zh="聽故事" pinyin="Tīng gùshì" en="Listen & retell" />
                  </button>
                </li>
              )}
            </>
          )}

          <li>
            <button
              type="button"
              className="nav-link nav-color-mode"
              onClick={toggleColorMode}
              aria-pressed={colorMode === "dark"}
              title={colorMode === "dark" ? "Switch to light mode" : "Switch to dark mode"}
            >
              {colorMode === "dark" ? (
                <BiLabel zh="☀️ 亮色" pinyin="Liàngsè" en="Light" />
              ) : (
                <BiLabel zh="🌙 深色" pinyin="Shēnsè" en="Dark" />
              )}
            </button>
          </li>

          {activeRole && (
            <li>
              <button type="button" className="nav-link logout" onClick={onLogout}>
                <BiLabel k="log_out" />
              </button>
            </li>
          )}
        </ul>
      </div>
    </nav>
  );
}
