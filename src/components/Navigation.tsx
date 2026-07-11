import "./Navigation.css";
import { Page } from "../types/page";
import { LoginRole } from "../pages/LoginPage";
import { BiLabel } from "./BiLabel";
import ToneMark from "./ToneMark";
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
   * pre-login nav items and logo target make sense for each. */
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
  const isStudent = activeRole === "student";
  const isTeacher = activeRole === "teacher";
  const logoTarget: Page =
    appVariant === "teacher" ? (isTeacher ? "teacher-dashboard" : "teacher-login") : "home";

  return (
    <nav className="navbar">
      <div className="navbar-container">
        <button
          type="button"
          className="navbar-logo"
          onClick={() => onNavigate(logoTarget)}
        >
          <img className="logo-icon" src="/logo.png" alt="Enjoyable Mandarin logo" />
          <span>Enjoyable Mandarin</span>
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
              <li>
                <a className="nav-link" href={`${import.meta.env.BASE_URL}teacher.html`}>
                  <BiLabel k="teacher_login" />
                </a>
              </li>
            </>
          )}

          {!compact && !activeRole && appVariant === "teacher" && (
            <li>
              <a className="nav-link" href={import.meta.env.BASE_URL}>
                <BiLabel zh="返回學生網站" pinyin="Fǎnhuí xuéshēng wǎngzhàn" en="Back to student site" />
              </a>
            </li>
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
                  <BiLabel zh="我的故事" pinyin="Wǒ de gùshì" en="My Stories" />
                </button>
              </li>

            </>
          )}

          {!compact && isTeacher && (
            <>
              <li>
                <button
                  type="button"
                  className={`nav-link ${currentPage === "teacher-dashboard" ? "active" : ""}`}
                  onClick={() => onNavigate("teacher-dashboard")}
                >
                  <BiLabel k="dashboard" />
                </button>
              </li>
              <li>
                <button
                  type="button"
                  className={`nav-link ${currentPage === "teacher-image-builder" ? "active" : ""}`}
                  onClick={() => onNavigate("teacher-image-builder")}
                >
                  <BiLabel k="image_builder" />
                </button>
              </li>
            </>
          )}

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
