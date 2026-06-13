import "./HomePage.css";
import { Page } from "../App";

interface HomePageProps {
  onNavigate: (page: Page) => void;
}

export default function HomePage({ onNavigate }: HomePageProps) {
  return (
    <div className="home-page">
      <section className="hero">
        <div className="hero-content">
          <p className="platform-kicker">Mandarin speaking practice</p>
          <h1 className="hero-title">Mandarin Story Coach</h1>
          <p className="hero-subtitle">
            Build better Chinese stories with picture prompts, voice recording,
            pronunciation feedback, and helpful language coaching.
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
            <span className="portal-title">Student Portal</span>
            <span className="portal-title-cn">學生入口</span>
            <span className="portal-description">
              Complete picture-based story tasks, record Mandarin speech, and
              review Praat plus AI feedback.
            </span>
            <span className="portal-arrow">›</span>
          </button>

          <button
            type="button"
            className="portal-card teacher-card"
            onClick={() => onNavigate("teacher-login")}
          >
            <span className="portal-icon">師</span>
            <span className="portal-title">Teacher Portal</span>
            <span className="portal-title-cn">教師入口</span>
            <span className="portal-description">
              Monitor student recordings, inspect speech metrics, and support
              narrative development.
            </span>
            <span className="portal-arrow">›</span>
          </button>
        </div>
      </section>

    </div>
  );
}
