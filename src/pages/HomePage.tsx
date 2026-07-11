import "./HomePage.css";
import { Page } from "../types/page";
import { BiLabel, BiText } from "../components/BiLabel";
import "../components/BiLabel.css";

interface HomePageProps {
  onNavigate: (page: Page) => void;
}

// "普通話故事老師" (Pǔtōnghuà gùshì lǎoshī) with each character's real tone,
// so the hero title's entrance animation is drawn from the actual pitch
// contour of its own tones (3-1-4-4-4-3-1) rather than a generic bounce —
// the same flat/rising/dip/falling shapes as ToneMark, performed by the
// headline itself.
const HERO_TITLE_CHARS: Array<{ char: string; tone: 1 | 2 | 3 | 4 }> = [
  { char: "普", tone: 3 },
  { char: "通", tone: 1 },
  { char: "話", tone: 4 },
  { char: "故", tone: 4 },
  { char: "事", tone: 4 },
  { char: "老", tone: 3 },
  { char: "師", tone: 1 },
];

// The 4-color tone rotation, reused for the stat chips and step numbers so
// the whole page — not just the hero title — reads as built from the same
// four tones instead of an arbitrary palette.
const TONE_ROTATION = ["tone-1", "tone-2", "tone-3", "tone-4"] as const;

const STATS: Array<{ zh: string; pinyin: string; en: string }> = [
  { zh: "4 個聲調", pinyin: "4 ge shēngdiào", en: "4 tones" },
  { zh: "6 個場景", pinyin: "6 ge chǎngjǐng", en: "6 scenes a story" },
  { zh: "AI 馬上回饋", pinyin: "AI mǎshàng huíkuì", en: "AI feedback right away" },
];

const HOW_IT_WORKS: Array<{
  icon: string;
  zh: string;
  pinyin: string;
  en: string;
  descZh: string;
  descPinyin: string;
  descEn: string;
}> = [
  {
    icon: "🖼️",
    zh: "選場景",
    pinyin: "Xuǎn chǎngjǐng",
    en: "Pick a scene",
    descZh: "挑一張圖片開始練習。",
    descPinyin: "Tiāo yì zhāng túpiàn kāishǐ liànxí.",
    descEn: "Choose a picture to start practicing.",
  },
  {
    icon: "🎙️",
    zh: "錄音練習",
    pinyin: "Lùyīn liànxí",
    en: "Record & practice",
    descZh: "說中文，錄下你的聲音。",
    descPinyin: "Shuō Zhōngwén, lù xià nǐ de shēngyīn.",
    descEn: "Speak Mandarin and record your voice.",
  },
  {
    icon: "⭐",
    zh: "看回饋",
    pinyin: "Kàn huíkuì",
    en: "Get feedback",
    descZh: "馬上看你的聲調和分數。",
    descPinyin: "Mǎshàng kàn nǐ de shēngdiào hé fēnshù.",
    descEn: "See your tone and score right away.",
  },
];

export default function HomePage({ onNavigate }: HomePageProps) {
  return (
    <div className="home-page">
      <section className="hero">
        <div className="hero-content">
          <p className="platform-kicker"><BiLabel k="mandarin_speaking_practice" /></p>
          <h1 className="hero-title">
            <span className="bi-label">
              <span className="bi-zh hero-title-zh" lang="zh-Hant" aria-label="普通話故事老師">
                {HERO_TITLE_CHARS.map(({ char, tone }, i) => (
                  <span
                    key={i}
                    className={`hero-char tone-${tone}`}
                    style={{ "--i": i } as React.CSSProperties}
                    aria-hidden="true"
                  >
                    <span className="hero-char-inner">{char}</span>
                  </span>
                ))}
              </span>
              <span className="bi-pinyin">Pǔtōnghuà gùshì lǎoshī</span>
              <small className="bi-en" lang="en">Mandarin Story Coach</small>
            </span>
          </h1>
          <p className="hero-subtitle">
            <BiText k="build_better_chinese_stories_with_pictur" />
          </p>

          <ul className="hero-stats" aria-label="At a glance">
            {STATS.map((stat, i) => (
              <li
                key={stat.en}
                className={`hero-stat-chip ${TONE_ROTATION[i % TONE_ROTATION.length]}`}
              >
                <BiLabel zh={stat.zh} pinyin={stat.pinyin} en={stat.en} />
              </li>
            ))}
          </ul>
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

          <a
            className="portal-card teacher-card"
            href={`${import.meta.env.BASE_URL}teacher.html`}
          >
            <span className="portal-icon">師</span>
            <span className="portal-title"><BiLabel k="teacher_portal" /></span>
            <span className="portal-description">
              <BiText k="monitor_student_recordings_inspect_speec" />
            </span>
            <span className="portal-arrow">›</span>
          </a>
        </div>
      </section>

      <section className="how-it-works" aria-label="How it works">
        <p className="how-it-works-kicker">
          <BiLabel zh="怎麼玩" pinyin="Zěnme wán" en="How it works" />
        </p>
        <ol className="how-it-works-grid">
          {HOW_IT_WORKS.map((step, i) => (
            <li
              key={step.en}
              className={`how-it-works-tile ${TONE_ROTATION[i % TONE_ROTATION.length]}`}
            >
              <span className="how-it-works-num" aria-hidden="true">
                {String(i + 1).padStart(2, "0")}
              </span>
              <span className="how-it-works-icon" aria-hidden="true">{step.icon}</span>
              <strong className="how-it-works-title">
                <BiLabel zh={step.zh} pinyin={step.pinyin} en={step.en} />
              </strong>
              <span className="how-it-works-desc">
                <BiText zh={step.descZh} pinyin={step.descPinyin} en={step.descEn} />
              </span>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
