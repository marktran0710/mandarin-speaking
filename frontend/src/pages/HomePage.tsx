import type { CSSProperties } from "react";
import "./HomePage.css";
import { Page } from "../types/page";
import { BiLabel, BiText } from "../components/BiLabel";
import ToneStroke from "../components/ToneStroke";
import "../components/BiLabel.css";

interface HomePageProps {
  onNavigate: (page: Page) => void;
}

const HERO_TITLE_CHARS: Array<{ char: string; tone: 1 | 2 | 3 | 4 }> = [
  { char: "慢", tone: 4 },
  { char: "慢", tone: 4 },
  { char: "中", tone: 1 },
  { char: "文", tone: 2 },
];

const SKILLS: Array<{ zh: string; pinyin: string; en: string }> = [
  { zh: "發音", pinyin: "Fāyīn", en: "Pronunciation" },
  { zh: "生詞", pinyin: "Shēngcí", en: "Vocabulary" },
  { zh: "應用", pinyin: "Yìngyòng", en: "Practical use" },
];

/* Four compact scenes keep the preview visual without asking one image to fill
   a large hero frame. The grid is intentionally data-driven so every card
   shares the same sizing and crop behavior. */
const STORY_SCENES = [
  { file: "street-conversation.png", className: "image-one" },
  { file: "missing-cat-card.png", className: "image-two" },
  { file: "campus-chat.png", className: "image-three" },
  { file: "park.svg", className: "image-four" },
];

const STATS: Array<{ zh: string; pinyin: string; en: string }> = [
  { zh: "4 個聲調", pinyin: "4 ge shēngdiào", en: "4 tones" },
  { zh: "6 個部分", pinyin: "6 ge bùfen", en: "6 scenes a story" },
  {
    zh: "AI 馬上回饋",
    pinyin: "AI mǎshàng huíkuì",
    en: "AI feedback right away",
  },
];

const HOW_IT_WORKS: Array<{
  zh: string;
  pinyin: string;
  en: string;
  descZh: string;
  descPinyin: string;
  descEn: string;
}> = [
  {
    zh: "看圖片",
    pinyin: "Kàn túpiàn",
    en: "Look",
    descZh: "先看清楚圖片，找出故事裡的人、地點和動作。",
    descPinyin:
      "Xiān kàn qīngchǔ túpiàn, zhǎo chū gùshì lǐ de rén, dìdiǎn hé dòngzuò.",
    descEn: "Study the scene and notice who, where, and what happens.",
  },
  {
    zh: "說故事",
    pinyin: "Shuō gùshì",
    en: "Speak",
    descZh: "說一句中文，錄下來，把圖片變成故事。",
    descPinyin:
      "Shuō yí jù Zhōngwén, lù xiàlái, bǎ túpiàn biànchéng gùshì.",
    descEn: "Record your Mandarin and turn the picture into a story.",
  },
  {
    zh: "看回饋",
    pinyin: "Kàn huíkuì",
    en: "Improve",
    descZh: "看看小提醒，再說一次會更自然。",
    descPinyin:
      "Kànkan xiǎo tíxǐng, zài shuō yí cì huì gèng zìrán.",
    descEn: "Review tone, rhythm, and vocabulary feedback before trying again.",
  },
];

export default function HomePage({ onNavigate }: HomePageProps) {
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
            <span className="hero-title-meta">
              <span className="hero-title-pinyin">Mànmàn Zhōngwén</span>
              <span className="hero-title-en">Mandarin, little by little</span>
            </span>
          </h1>

          <p className="hero-subtitle">
            <BiText k="build_better_chinese_stories_with_pictur" />
          </p>

          <ul className="hero-stats" aria-label="At a glance">
            {STATS.map((stat) => (
              <li key={stat.en} className="hero-stat-chip">
                <BiLabel zh={stat.zh} pinyin={stat.pinyin} en={stat.en} />
              </li>
            ))}
          </ul>

          <button
            type="button"
            className="hero-primary-action"
            onClick={() => onNavigate("student-login")}
          >
            <BiLabel zh="開始學習" pinyin="Kāishǐ xuéxí" en="Start Learning" />
            <span aria-hidden="true">→</span>
          </button>
        </div>

        <div className="home-hero-visual" aria-label="Story practice preview">
          <div className="story-preview-stage">
            <div className="story-preview-scenes" aria-hidden="true">
              {STORY_SCENES.map(({ file, className }) => (
                <img
                  key={className}
                  src={`/sample-scenes/${file}`}
                  alt=""
                  className={`story-preview-image ${className}`}
                />
              ))}
            </div>

            <div
              className="vertical-title"
              lang="zh-Hant"
              aria-label="發音 Pronunciation, 生詞 Vocabulary, 應用 Practical use"
            >
              {SKILLS.map((skill, gi) => (
                <div
                  className="vertical-title-group"
                  key={skill.en}
                  title={`${skill.pinyin} · ${skill.en}`}
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

      <section className="how-it-works" aria-label="How it works">
        <p className="how-it-works-kicker">
          <span lang="zh-Hant">三步開始</span>
          <span className="how-it-works-kicker-meta">
            Sān bù kāishǐ · Three steps
          </span>
        </p>
        <ol className="how-it-works-grid">
          {HOW_IT_WORKS.map((step, i) => (
            <li key={step.en} className="how-it-works-tile">
              <span className="how-it-works-num" aria-hidden="true">
                {String(i + 1).padStart(2, "0")}
              </span>
              <strong className="how-it-works-title">
                <BiLabel zh={step.zh} pinyin={step.pinyin} en={step.en} />
              </strong>
              <span className="how-it-works-desc">
                <BiText
                  zh={step.descZh}
                  pinyin={step.descPinyin}
                  en={step.descEn}
                />
              </span>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
