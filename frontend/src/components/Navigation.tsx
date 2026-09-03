import "./Navigation.css";
import { Page } from "../types/page";
import { LoginRole } from "../pages/LoginPage";
import { BiLabel } from "./BiLabel";
import ToneMark from "./tone/ToneMark";
import StudentIcon from "./StudentIcon";
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
}

export default function Navigation({
  currentPage,
  activeRole,
  onNavigate,
  onLogout,
  compact = false,
  appVariant = "student",
}: NavigationProps) {
  const [colorMode, toggleColorMode] = useColorMode();
  const isStudent = activeRole === "student";
  // The teacher app renders this bar only on its login screen (once logged
  // in, ManagementShell's own topbar takes over), so the teacher logo has just
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

        <ul className={`navbar-menu navbar-menu-${appVariant}`}>
          {!compact && !activeRole && appVariant === "student" && (
            <>
              <li>
                <button
                  type="button"
                  className={`nav-link ${currentPage === "home" ? "active" : ""}`}
                  onClick={() => onNavigate("home")}
                >
                  {appVariant === "student" && <span className="nav-link-icon"><StudentIcon name="home" /></span>}
                  <BiLabel k="portals" />
                </button>
              </li>
              <li>
                <button
                  type="button"
                  className={`nav-link ${currentPage === "student-login" ? "active" : ""}`}
                  onClick={() => onNavigate("student-login")}
                >
                  {appVariant === "student" && <span className="nav-link-icon"><StudentIcon name="voice" /></span>}
                  <BiLabel k="student_login" />
                </button>
              </li>
            </>
          )}

          {!compact && isStudent && (
            <li>
              <button
                type="button"
                className={`nav-link ${currentPage === "student-workspace" || currentPage === "student-practice" || currentPage === "student-stories" ? "active" : ""}`}
                onClick={() => onNavigate("student-workspace")}
              >
                <span className="nav-link-icon"><StudentIcon name="home" /></span>
                <BiLabel zh="我的學習" pinyin="Wǒ de xuéxí" en="My learning" />
              </button>
            </li>
          )}

          <li>
            <button
              type="button"
              className="nav-link nav-color-mode"
              onClick={toggleColorMode}
              aria-pressed={colorMode === "dark"}
              title={colorMode === "dark" ? "Switch to light mode" : "Switch to dark mode"}
            >
              {appVariant === "student" && <span className="nav-link-icon"><StudentIcon name={colorMode === "dark" ? "sun" : "moon"} /></span>}
              {colorMode === "dark" ? (
                <BiLabel zh="亮色" pinyin="Liàngsè" en="Light" />
              ) : (
                <BiLabel zh="深色" pinyin="Shēnsè" en="Dark" />
              )}
            </button>
          </li>

          {activeRole && (
            <li>
              <button type="button" className="nav-link logout" onClick={onLogout}>
                {appVariant === "student" && <span className="nav-link-icon"><StudentIcon name="logout" /></span>}
                <BiLabel k="log_out" />
              </button>
            </li>
          )}
        </ul>
      </div>
    </nav>
  );
}
