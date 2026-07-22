import type { CSSProperties } from "react";
import "./HomePage.css";
import { Page } from "../types/page";
import { BiLabel, BiText } from "../components/BiLabel";
import "../components/BiLabel.css";

interface HomePageProps {
  onNavigate: (page: Page) => void;
}

const HERO_TITLE_CHARS: Array<{ char: string; tone: 1 | 2 | 3 | 4 }> = [
  { char: "普", tone: 3 },
  { char: "通", tone: 1 },
  { char: "話", tone: 4 },
  { char: "故", tone: 4 },
  { char: "事", tone: 4 },
  { char: "老", tone: 3 },
  { char: "師", tone: 1 },
];

const TONE_ROTATION = ["tone-1", "tone-2", "tone-3", "tone-4"] as const;

const VERTICAL_TITLE_SKILLS: Array<{
  zh: string;
  pinyin: string;
  en: string;
  chars: Array<{ char: string; tone: 1 | 2 | 3 | 4 }>;
}> = [
  {
    zh: "發音",
    pinyin: "Fāyīn",
    en: "Pronunciation",
    chars: [
      { char: "發", tone: 1 },
      { char: "音", tone: 1 },
    ],
  },
  {
    zh: "生詞",
    pinyin: "Shēngcí",
    en: "Vocabulary",
    chars: [
      { char: "生", tone: 1 },
      { char: "詞", tone: 2 },
    ],
  },
  {
    zh: "應用",
    pinyin: "Yìngyòng",
    en: "Practical use",
    chars: [
      { char: "應", tone: 4 },
      { char: "用", tone: 4 },
    ],
  },
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
    descZh: "用普通話錄下你的句子，練習把圖片變成故事。",
    descPinyin:
      "Yòng Pǔtōnghuà lù xià nǐ de jùzi, liànxí bǎ túpiàn biànchéng gùshì.",
    descEn: "Record your Mandarin and turn the picture into a story.",
  },
  {
    zh: "看回饋",
    pinyin: "Kàn huíkuì",
    en: "Improve",
    descZh: "檢查聲調、節奏和生詞，再錄一次會更自然。",
    descPinyin:
      "Jiǎnchá shēngdiào, jiézòu hé shēngcí, zài lù yí cì huì gèng zìrán.",
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
              aria-label="普通話故事老師"
            >
              {HERO_TITLE_CHARS.map(({ char, tone }, i) => (
                <span
                  key={char}
                  className={`hero-char tone-${tone}`}
                  style={{ "--i": i } as CSSProperties}
                  aria-hidden="true"
                >
                  {char}
                </span>
              ))}
            </span>
            <span className="hero-title-meta">
              <span className="hero-title-pinyin">Pǔtōnghuà gùshì lǎoshī</span>
              <span className="hero-title-en">Mandarin Story Coach</span>
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

        <div className="home-hero-visual" aria-label="Story practice preview">
          <div className="story-preview-stage">
            <div className="story-preview-scenes" aria-hidden="true">
              <img
                src={`${import.meta.env.BASE_URL}sample-scenes/street-conversation.png`}
                alt=""
                className="story-preview-image image-one"
              />
              <img
                src={`${import.meta.env.BASE_URL}sample-scenes/missing-cat-card.png`}
                alt=""
                className="story-preview-image image-two"
              />
              <img
                src={`${import.meta.env.BASE_URL}sample-scenes/campus-chat.png`}
                alt=""
                className="story-preview-image image-three"
              />
            </div>

            <div
              className="vertical-title"
              lang="zh-Hant"
              aria-label="發音 Pronunciation, 生詞 Vocabulary, 應用 Practical use"
            >
              {VERTICAL_TITLE_SKILLS.map((skill, gi) => (
                <div
                  className="vertical-title-group"
                  key={skill.en}
                  title={`${skill.pinyin} · ${skill.en}`}
                >
                  {skill.chars.map(({ char, tone }, i) => (
                    <span
                      key={char}
                      className={`vertical-title-char tone-${tone}`}
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

      <div className="home-cta">
        <button
          type="button"
          className="hero-primary-action"
          onClick={() => onNavigate("student-login")}
        >
          <BiLabel zh="開始學習" pinyin="Kāishǐ xuéxí" en="Start Learning" />
          <span aria-hidden="true">→</span>
        </button>
      </div>

      <section className="how-it-works" aria-label="How it works">
        <p className="how-it-works-kicker">
          <BiLabel zh="三步開始" pinyin="Sān bù kāishǐ" en="Three-step flow" />
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
