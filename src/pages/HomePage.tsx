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
          <p className="platform-kicker">Research Platform</p>
          <h1 className="hero-title">Chinese Narrative Competence</h1>
          <p className="hero-subtitle">
            Master's/Ph.D. thesis experimental tool for Mandarin storytelling,
            speech analysis, and guided practice.
          </p>
        </div>
      </section>

      <section className="portal-section" aria-label="Learning portals">
        <div className="portal-grid">
          <button
            type="button"
            className="portal-card student-card"
            onClick={() => onNavigate("create")}
          >
            <span className="portal-icon">學</span>
            <span className="portal-title">Student Portal</span>
            <span className="portal-title-cn">學生入口</span>
            <span className="portal-description">
              Take assessments and complete gamified training activities
            </span>
            <span className="portal-arrow">›</span>
          </button>

          <button
            type="button"
            className="portal-card teacher-card"
            onClick={() => onNavigate("mystories")}
          >
            <span className="portal-icon">師</span>
            <span className="portal-title">Review Portal</span>
            <span className="portal-title-cn">練習紀錄</span>
            <span className="portal-description">
              Review saved recordings, tone metrics, and AI coaching feedback
            </span>
            <span className="portal-arrow">›</span>
          </button>
        </div>
      </section>

      <section className="features">
        <div className="features-container">
          <h2>Practice flow</h2>
          <div className="features-grid">
            <div className="feature-card blue">
              <div className="feature-icon">1</div>
              <h3>Choose a prompt</h3>
              <p>Select a topic image and vocabulary set before recording.</p>
            </div>

            <div className="feature-card green">
              <div className="feature-icon">2</div>
              <h3>Record speech</h3>
              <p>Speak Mandarin and capture a clean WAV sample for analysis.</p>
            </div>

            <div className="feature-card purple">
              <div className="feature-icon">3</div>
              <h3>Study feedback</h3>
              <p>Compare Praat tone metrics with AI language-coach guidance.</p>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
