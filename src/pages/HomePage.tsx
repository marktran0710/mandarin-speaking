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
          <p className="platform-kicker"><BiLabel zh="普通話口語練習" en="Mandarin speaking practice" /></p>
          <h1 className="hero-title"><BiLabel zh="普通話故事教練" en="Mandarin Story Coach" /></h1>
          <p className="hero-subtitle">
            <BiText
              zh="用圖片提示、語音錄製、發音回饋和語言指導，打造更好的中文故事。"
              en="Build better Chinese stories with picture prompts, voice recording, pronunciation feedback, and helpful language coaching."
            />
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
            <span className="portal-title"><BiLabel zh="學生入口" en="Student Portal" /></span>
            <span className="portal-description">
              <BiText zh="完成圖片故事任務、錄製普通話語音，並查看 Praat 及 AI 回饋。" en="Complete picture-based story tasks, record Mandarin speech, and review Praat plus AI feedback." />
            </span>
            <span className="portal-arrow">›</span>
          </button>

          <button
            type="button"
            className="portal-card teacher-card"
            onClick={() => onNavigate("teacher-login")}
          >
            <span className="portal-icon">師</span>
            <span className="portal-title"><BiLabel zh="教師入口" en="Teacher Portal" /></span>
            <span className="portal-description">
              <BiText zh="監控學生錄音、查看語音指標，並支援敘事發展。" en="Monitor student recordings, inspect speech metrics, and support narrative development." />
            </span>
            <span className="portal-arrow">›</span>
          </button>
        </div>
      </section>

    </div>
  );
}
