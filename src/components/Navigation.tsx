import "./Navigation.css";
import { Page } from "../App";

interface NavigationProps {
  currentPage: Page;
  onNavigate: (page: Page) => void;
}

export default function Navigation({
  currentPage,
  onNavigate,
}: NavigationProps) {
  return (
    <nav className="navbar">
      <div className="navbar-container">
        <div className="navbar-logo">
          <span className="logo-icon">🎤</span>
          <span>Mandarin Stories</span>
        </div>

        <ul className="navbar-menu">
          <li>
            <button
              className={`nav-link ${currentPage === "home" ? "active" : ""}`}
              onClick={() => onNavigate("home")}
            >
              🏠 Home
            </button>
          </li>
          <li>
            <button
              className={`nav-link ${currentPage === "create" ? "active" : ""}`}
              onClick={() => onNavigate("create")}
            >
              ✨ Create Story
            </button>
          </li>
          <li>
            <button
              className={`nav-link ${currentPage === "mystories" ? "active" : ""}`}
              onClick={() => onNavigate("mystories")}
            >
              📚 My Stories
            </button>
          </li>
        </ul>
      </div>
    </nav>
  );
}
