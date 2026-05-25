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

      <section className="features">
        <div className="features-container">
          <h2>Learning workflow</h2>
          <div className="features-grid">
            <div className="feature-card blue">
              <div className="feature-icon">1</div>
              <h3>Plan with visual prompts</h3>
              <p>Students choose a topic, inspect picture prompts, and prepare target vocabulary.</p>
            </div>

            <div className="feature-card green">
              <div className="feature-icon">2</div>
              <h3>Record narrative speech</h3>
              <p>Each attempt is linked to a picture so practice evidence stays organized.</p>
            </div>

            <div className="feature-card purple">
              <div className="feature-icon">3</div>
              <h3>Review measurable feedback</h3>
              <p>Praat visualizes prosody while Gemini supports fluency, grammar, and vocabulary reflection.</p>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
