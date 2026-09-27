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
  { file: "street-conversation.png", className: "image-one" },
  { file: "missing-cat-card.png", className: "image-two" },
  { file: "campus-chat.png", className: "image-three" },
  { file: "afternoon-tea-material.png", className: "image-four" },
];

const STATS: Array<{ key: "fourTones" | "sixScenes" | "aiFeedback" }> = [
  { key: "fourTones" },
  { key: "sixScenes" },
  { key: "aiFeedback" },
];

const HOW_IT_WORKS: Array<{
  zh: string;
  descZh: string;
}> = [
  {
    zh: "看圖片",
    descZh: "先看清楚圖片，找出故事裡的人、地點和動作。",
  },
  {
    zh: "說故事",
    descZh: "說一句中文，錄下來，把圖片變成故事。",
  },
  {
    zh: "看回饋",
    descZh: "看看小提醒，再說一次會更自然。",
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
    <div className="home-page">
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
            <span className="hero-title-meta"><StudentSystemText k="brand" /></span>
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
              {STORY_SCENES.map(({ file, className }) => (
                <img
                  key={className}
                  src={`/sample-scenes/${file}`}
                  alt=""
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

      <section className="how-it-works" aria-label="使用方式">
        <p className="how-it-works-kicker">
          <StudentSystemText k="threeSteps" />
        </p>
        <ol className="how-it-works-grid">
          {HOW_IT_WORKS.map((step, i) => (
            <li key={step.zh} className="how-it-works-tile">
              <span className="how-it-works-num" aria-hidden="true">
                {String(i + 1).padStart(2, "0")}
              </span>
              <strong className="how-it-works-title">
                <StudentSystemText k={i === 0 ? "lookAtImages" : i === 1 ? "tellStory" : "seeFeedback"} />
              </strong>
              <span className="how-it-works-desc">
                {step.descZh}
              </span>
            </li>
          ))}
        </ol>
      </section>
      <SourceAttribution />
    </div>
  );
}
