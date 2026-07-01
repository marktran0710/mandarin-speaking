import "./Navigation.css";
import { Page } from "../App";
import { LoginRole } from "../pages/LoginPage";
import { BiLabel } from "./BiLabel";
import "./BiLabel.css";

interface NavigationProps {
  currentPage: Page;
  activeRole: LoginRole | null;
  onNavigate: (page: Page) => void;
  onLogout: () => void;
}

export default function Navigation({
  currentPage,
  activeRole,
  onNavigate,
  onLogout,
}: NavigationProps) {
  const isStudent = activeRole === "student";
  const isTeacher = activeRole === "teacher";

  return (
    <nav className="navbar">
      <div className="navbar-container">
        <button
          type="button"
          className="navbar-logo"
          onClick={() => onNavigate("home")}
        >
          <img className="logo-icon" src="/logo.png" alt="Enjoyable Mandarin logo" />
          <span>Enjoyable Mandarin</span>
        </button>

        <ul className="navbar-menu">
          {!activeRole && (
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
                <button
                  type="button"
                  className={`nav-link ${currentPage === "teacher-login" ? "active" : ""}`}
                  onClick={() => onNavigate("teacher-login")}
                >
                  <BiLabel k="teacher_login" />
                </button>
              </li>
            </>
          )}

          {isStudent && (
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

            </>
          )}

          {isTeacher && (
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
