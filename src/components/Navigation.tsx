import "./Navigation.css";
import { Page } from "../App";
import { LoginRole } from "../pages/LoginPage";

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
          <span className="logo-icon">M</span>
          <span>Mandarin Stories</span>
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
                  Portals
                </button>
              </li>
              <li>
                <button
                  type="button"
                  className={`nav-link ${currentPage === "student-login" ? "active" : ""}`}
                  onClick={() => onNavigate("student-login")}
                >
                  Student Login
                </button>
              </li>
              <li>
                <button
                  type="button"
                  className={`nav-link ${currentPage === "teacher-login" ? "active" : ""}`}
                  onClick={() => onNavigate("teacher-login")}
                >
                  Teacher Login
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
                  Training
                </button>
              </li>
              <li>
                <button
                  type="button"
                  className={`nav-link ${currentPage === "student-stories" ? "active" : ""}`}
                  onClick={() => onNavigate("student-stories")}
                >
                  My Stories
                </button>
              </li>
              <li>
                <button
                  type="button"
                  className={`nav-link ${currentPage === "voice-test" ? "active" : ""}`}
                  onClick={() => onNavigate("voice-test")}
                >
                  Voice Test
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
                  Dashboard
                </button>
              </li>
              <li>
                <button
                  type="button"
                  className={`nav-link ${currentPage === "teacher-image-builder" ? "active" : ""}`}
                  onClick={() => onNavigate("teacher-image-builder")}
                >
                  Image Builder
                </button>
              </li>
            </>
          )}

          {activeRole && (
            <li>
              <button type="button" className="nav-link logout" onClick={onLogout}>
                Log out
              </button>
            </li>
          )}
        </ul>
      </div>
    </nav>
  );
}
