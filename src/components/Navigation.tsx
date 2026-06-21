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
                  <BiLabel zh="入口" en="Portals" />
                </button>
              </li>
              <li>
                <button
                  type="button"
                  className={`nav-link ${currentPage === "student-login" ? "active" : ""}`}
                  onClick={() => onNavigate("student-login")}
                >
                  <BiLabel zh="學生登入" en="Student Login" />
                </button>
              </li>
              <li>
                <button
                  type="button"
                  className={`nav-link ${currentPage === "teacher-login" ? "active" : ""}`}
                  onClick={() => onNavigate("teacher-login")}
                >
                  <BiLabel zh="教師登入" en="Teacher Login" />
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
                  <BiLabel zh="訓練" en="Training" />
                </button>
              </li>
              <li>
                <button
                  type="button"
                  className={`nav-link ${currentPage === "image-narration" ? "active" : ""}`}
                  onClick={() => onNavigate("image-narration")}
                >
                  Describe the Picture
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
                  <BiLabel zh="儀表板" en="Dashboard" />
                </button>
              </li>
              <li>
                <button
                  type="button"
                  className={`nav-link ${currentPage === "teacher-image-builder" ? "active" : ""}`}
                  onClick={() => onNavigate("teacher-image-builder")}
                >
                  <BiLabel zh="圖片產生器" en="Image Builder" />
                </button>
              </li>
            </>
          )}

          {activeRole && (
            <li>
              <button type="button" className="nav-link logout" onClick={onLogout}>
<BiLabel zh="登出" en="Log out" />
              </button>
            </li>
          )}
        </ul>
      </div>
    </nav>
  );
}
