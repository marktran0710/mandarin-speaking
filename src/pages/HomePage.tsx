import "./HomePage.css";
import { Page } from "../App";

interface HomePageProps {
  onNavigate: (page: Page) => void;
}

export default function HomePage({ onNavigate }: HomePageProps) {
  return (
    <div className="home-page">
      {/* Hero Section */}
      <section className="hero">
        <div className="hero-content">
          <h1 className="hero-title">Learn Mandarin Through Storytelling</h1>
          <p className="hero-subtitle">
            Create, record, and improve your Mandarin pronunciation with
            AI-powered feedback
          </p>
          <button className="hero-cta" onClick={() => onNavigate("create")}>
            🚀 Start Creating Stories
          </button>
        </div>
      </section>

      {/* Features Section */}
      <section className="features">
        <div className="features-container">
          <h2>Why Learn with Mandarin Stories?</h2>
          <div className="features-grid">
            <div className="feature-card red">
              <div className="feature-icon">🎤</div>
              <h3>Real-time Feedback</h3>
              <p>
                Get instant AI feedback on your pronunciation, tone, and fluency
              </p>
            </div>

            <div className="feature-card yellow">
              <div className="feature-icon">📚</div>
              <h3>Learn by Topics</h3>
              <p>
                Explore engaging themes: Adventure, Nature, Fantasy, School, and
                more
              </p>
            </div>

            <div className="feature-card cyan">
              <div className="feature-icon">✨</div>
              <h3>Vocabulary Building</h3>
              <p>Discover and practice new Chinese words with each story</p>
            </div>

            <div className="feature-card green">
              <div className="feature-icon">📊</div>
              <h3>Track Progress</h3>
              <p>
                Monitor your improvement with detailed analytics and metrics
              </p>
            </div>

            <div className="feature-card purple">
              <div className="feature-icon">🎵</div>
              <h3>Tone Practice</h3>
              <p>Master the four tones with visual pitch tracking</p>
            </div>

            <div className="feature-card blue">
              <div className="feature-icon">💾</div>
              <h3>Save Your Stories</h3>
              <p>Keep all your recordings organized and review them anytime</p>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="cta-section">
        <div className="cta-container">
          <div className="cta-left">
            <h2>Ready to Master Mandarin?</h2>
            <p>
              Choose your favorite topic and start creating your first story
              today! Practice at your own pace with real-time feedback.
            </p>
          </div>
          <div className="cta-buttons">
            <button
              className="btn-primary"
              onClick={() => onNavigate("create")}
            >
              ✨ Create New Story
            </button>
            <button
              className="btn-secondary"
              onClick={() => onNavigate("mystories")}
            >
              📚 View My Stories
            </button>
          </div>
        </div>
      </section>

      {/* Stats Section */}
      <section className="stats">
        <div className="stats-container">
          <div className="stat-card">
            <div className="stat-number">6</div>
            <div className="stat-label">Topics</div>
          </div>
          <div className="stat-card">
            <div className="stat-number">24+</div>
            <div className="stat-label">Stories</div>
          </div>
          <div className="stat-card">
            <div className="stat-number">∞</div>
            <div className="stat-label">Learning</div>
          </div>
        </div>
      </section>
    </div>
  );
}
