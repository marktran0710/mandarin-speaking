import { useState, type CSSProperties } from "react";
import "./HomePage.css";
import { Page } from "../../types/page";
import ToneStroke from "../../components/tone/ToneStroke";
import StudentIcon from "../../components/navigation/StudentIcon";
import StudentSystemText from "@shared/ui/student/StudentSystemText";
import { studentUiCopy } from "../../i18n/student-ui-copy";
import SourceAttribution from "@shared/ui/SourceAttribution";

interface HomePageProps {
  onNavigate: (page: Page) => void;
}

const HERO_TITLE_CHARS: Array<{ char: string; tone: 1 | 2 | 3 | 4 }> = [
  { char: "慢", tone: 4 },
  { char: "慢", tone: 4 },
  { char: "中", tone: 1 },
  { char: "文", tone: 2 },
];

const SKILLS: Array<{ zh: string; key: "pronunciation" | "vocabulary" | "practicalUse" }> = [
  { zh: "發音", key: "pronunciation" },
  { zh: "生詞", key: "vocabulary" },
  { zh: "應用", key: "practicalUse" },
];

/* Four compact scenes keep the preview visual without asking one image to fill
   a large hero frame. The grid is intentionally data-driven so every card
   shares the same sizing and crop behavior. */
const STORY_SCENES = [
  { file: "street-conversation.png", className: "image-one", width: 357, height: 280 },
  { file: "missing-cat-card.png", className: "image-two", width: 397, height: 316 },
  { file: "campus-chat.png", className: "image-three", width: 395, height: 354 },
  { file: "afternoon-tea-material.png", className: "image-four", width: 1448, height: 1086 },
];

const STATS: Array<{ key: "fourTones" | "sixScenes" | "aiFeedback" }> = [
  { key: "fourTones" },
  { key: "sixScenes" },
  { key: "aiFeedback" },
];

const PRACTICE_FOCUS: Array<{
  key: "pronunciation" | "vocabulary" | "practicalUse";
  descZh: string;
}> = [
  {
    key: "pronunciation",
    descZh: "聽清楚聲調，知道下一次可以怎麼調整。",
  },
  {
    key: "vocabulary",
    descZh: "從圖片和情境記住真正會用到的詞語。",
  },
  {
    key: "practicalUse",
    descZh: "把學會的句子放進故事裡，慢慢說得自然。",
  },
];

export default function HomePage({ onNavigate }: HomePageProps) {
  // Each hero photo fetches independently; without this the entrance
  // animation below fires on a fixed clock and photos can pop in one by
  // one well after their frame has already animated onto the page.
  const [loadedScenes, setLoadedScenes] = useState<Set<string>>(() => new Set());
  const markSceneLoaded = (className: string) =>
    setLoadedScenes((prev) => (prev.has(className) ? prev : new Set(prev).add(className)));

  return (
    <div className="home-page" lang="zh-Hant">
      <section className="home-hero" aria-labelledby="home-hero-title">
        <div className="home-hero-copy">
          <h1 id="home-hero-title" className="hero-title">
            <span
              className="hero-title-zh"
              lang="zh-Hant"
              aria-label="慢慢中文"
            >
              {HERO_TITLE_CHARS.map(({ char, tone }, i) => (
                <span
                  key={`${char}-${i}`}
                  className={`hero-char tone-${tone}`}
                  style={{ "--i": i } as CSSProperties}
                  aria-hidden="true"
                >
                  {/* Each character wears its own tone contour: 慢 慢 中 文
                      is 4·4·1·2, so the row reads ＼ ＼ ￣ ／ — the name of
                      the app spelling out what the app teaches. */}
                  <ToneStroke
                    tone={tone}
                    className="hero-char-tone"
                    animated
                    delay={i * 0.09}
                  />
                  <span className="hero-char-glyph">{char}</span>
                </span>
              ))}
            </span>
            <span className="hero-title-meta">
              <StudentSystemText k="brand">Mànmàn Zhōngwén</StudentSystemText>
            </span>
          </h1>

          <p className="hero-subtitle">
            用圖片和聲音，慢慢說出你的中文故事。
          </p>

          <ul className="hero-stats" aria-label={studentUiCopy.atAGlance.zh}>
            {STATS.map((stat) => (
              <li key={stat.key} className="hero-stat-chip">
                <StudentSystemText k={stat.key} />
              </li>
            ))}
          </ul>

          <button
            type="button"
            className="hero-primary-action"
            onClick={() => onNavigate("student-login")}
          >
            <StudentSystemText k="startLearning" withinControl />
            <StudentIcon name="arrow-right" size={17} aria-hidden="true" />
          </button>
        </div>

        <div className="home-hero-visual" aria-label="故事練習預覽">
          <div className="story-preview-stage">
            <div className="story-preview-scenes" aria-hidden="true">
              {STORY_SCENES.map(({ file, className, width, height }, index) => (
                <img
                  key={className}
                  src={`/sample-scenes/${file}`}
                  alt=""
                  width={width}
                  height={height}
                  decoding="async"
                  {...(index === 0 ? { fetchpriority: "high" } : {})}
                  className={`story-preview-image ${className}${loadedScenes.has(className) ? " is-loaded" : ""}`}
                  onLoad={() => markSceneLoaded(className)}
                />
              ))}
            </div>

            <div
              className="vertical-title"
              lang="zh-Hant"
              aria-label="發音、生詞、應用"
            >
              {SKILLS.map((skill, gi) => (
                <div
                  className="vertical-title-group"
                  key={skill.key}
                >
                  {[...skill.zh].map((char, i) => (
                    <span
                      key={char}
                      className="vertical-title-char"
                      style={{ "--i": gi * 2 + i } as CSSProperties}
                      aria-hidden="true"
                    >
                      {char}
                    </span>
                  ))}
                </div>
              ))}
            </div>
          </div>
        </div>

      </section>

      <section className="practice-focus" aria-labelledby="practice-focus-title">
        <div className="practice-focus-heading">
          <p className="practice-focus-kicker">學習重點</p>
          <h2 id="practice-focus-title">從發音到應用，慢慢練成自然中文。</h2>
          <p>每次練習都會留下下一步，讓你知道該聽什麼、說什麼、再試一次什麼。</p>
        </div>
        <ul className="practice-focus-grid">
          {PRACTICE_FOCUS.map((focus, i) => (
            <li key={focus.key} className="practice-focus-card">
              <span className="practice-focus-index" aria-hidden="true">
                {String(i + 1).padStart(2, "0")}
              </span>
              <strong className="practice-focus-title">
                <StudentSystemText k={focus.key} />
              </strong>
              <p>{focus.descZh}</p>
            </li>
          ))}
        </ul>
      </section>

      <SourceAttribution />
    </div>
  );
}
