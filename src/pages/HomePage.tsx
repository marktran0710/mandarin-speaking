import "./HomePage.css";
import { Page } from "../App";
import { BiLabel, BiText } from "../components/BiLabel";
import "../components/BiLabel.css";

interface HomePageProps {
  onNavigate: (page: Page) => void;
}

export default function HomePage({ onNavigate }: HomePageProps) {
  return (
    <div className="home-page">
      <section className="hero">
        <div className="hero-content">
          <p className="platform-kicker"><BiLabel k="mandarin_speaking_practice" /></p>
          <h1 className="hero-title"><BiLabel k="mandarin_story_coach" /></h1>
          <p className="hero-subtitle">
            <BiText k="build_better_chinese_stories_with_pictur" />
          </p>
        </div>
      </section>

      <section className="portal-section" aria-label="Learning portals">
        <div className="portal-grid">
          <button
            type="button"
            className="portal-card student-card"
            onClick={() => onNavigate("student-login")}
          >
            <span className="portal-icon">學</span>
            <span className="portal-title"><BiLabel k="student_portal" /></span>
            <span className="portal-description">
              <BiText k="complete_picture_based_story_tasks_recor" />
            </span>
            <span className="portal-arrow">›</span>
          </button>

          <button
            type="button"
            className="portal-card teacher-card"
            onClick={() => onNavigate("teacher-login")}
          >
            <span className="portal-icon">師</span>
            <span className="portal-title"><BiLabel k="teacher_portal" /></span>
            <span className="portal-description">
              <BiText k="monitor_student_recordings_inspect_speec" />
            </span>
            <span className="portal-arrow">›</span>
          </button>
        </div>
      </section>

    </div>
  );
}
