import { useState } from "react";
import "./TopicSelector.css";

export interface Topic {
  id: string;
  name: string;
  description: string;
  skillFocus: string;
  level: string;
  images: string[];
  vocabulary: Record<number, string[]>;
}

interface TopicSelectorProps {
  onTopicSelect?: (topic: Topic) => void;
}

type SceneIcon =
  | "lantern"
  | "mountainTrain"
  | "temple"
  | "schoolFair"
  | "nightMarket"
  | "dragonBoat";

interface StoryScene {
  title: string;
  subtitle: string;
  sky: string;
  ground: string;
  accent: string;
  icon: SceneIcon;
}

function escapeSvgText(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function sceneIllustration(icon: SceneIcon, accent: string): string {
  const commonShadow = 'filter="url(#softShadow)"';
  const illustrations: Record<SceneIcon, string> = {
    lantern: `
      <path d="M74 92 C132 48 264 48 326 92" fill="none" stroke="${accent}" stroke-width="10" stroke-linecap="round" opacity="0.45"/>
      <g ${commonShadow}>
        <rect x="84" y="104" width="58" height="76" rx="22" fill="#ffcf56"/>
        <rect x="171" y="82" width="70" height="94" rx="26" fill="#ef6f6c"/>
        <rect x="270" y="112" width="52" height="68" rx="20" fill="#69c0b8"/>
      </g>
      <path d="M113 180 V202 M206 176 V202 M296 180 V202" stroke="#8a4f2f" stroke-width="5" stroke-linecap="round"/>
      <path d="M83 224 C120 204 172 210 202 226 C242 205 302 203 342 222" fill="none" stroke="#5b8c76" stroke-width="11" stroke-linecap="round"/>
      <circle cx="96" cy="230" r="17" fill="#f4b18b"/>
      <circle cx="152" cy="222" r="17" fill="#f7c59f"/>
      <circle cx="255" cy="226" r="17" fill="#d99c77"/>
      <circle cx="310" cy="220" r="17" fill="#f4b18b"/>
    `,
    mountainTrain: `
      <circle cx="318" cy="66" r="30" fill="#ffd166" opacity="0.95"/>
      <path d="M42 202 L126 104 L190 202 Z" fill="#6aa67f" ${commonShadow}/>
      <path d="M112 202 L226 72 L348 202 Z" fill="#4f8d78" ${commonShadow}/>
      <path d="M184 118 L226 72 L270 120 C238 108 215 109 184 118 Z" fill="#f7fafc"/>
      <path d="M54 226 C132 175 228 255 346 174" fill="none" stroke="#6f4e37" stroke-width="12" stroke-linecap="round"/>
      <rect x="124" y="178" width="122" height="42" rx="12" fill="${accent}" ${commonShadow}/>
      <rect x="142" y="188" width="22" height="16" rx="4" fill="#eff6ff"/>
      <rect x="174" y="188" width="22" height="16" rx="4" fill="#eff6ff"/>
      <rect x="206" y="188" width="22" height="16" rx="4" fill="#eff6ff"/>
      <circle cx="154" cy="224" r="8" fill="#1f2937"/>
      <circle cx="216" cy="224" r="8" fill="#1f2937"/>
    `,
    temple: `
      <path d="M72 112 C122 78 274 78 328 112" fill="none" stroke="${accent}" stroke-width="15" stroke-linecap="round"/>
      <path d="M96 128 H304 V216 H96 Z" fill="#fff4d6" ${commonShadow}/>
      <path d="M76 132 L200 72 L324 132" fill="none" stroke="#d9483b" stroke-width="18" stroke-linecap="round" stroke-linejoin="round"/>
      <rect x="126" y="150" width="48" height="66" rx="8" fill="#d9483b"/>
      <rect x="226" y="150" width="48" height="66" rx="8" fill="#d9483b"/>
      <circle cx="200" cy="156" r="24" fill="#ffd166"/>
      <path d="M185 184 C196 174 208 174 218 184 V216 H185 Z" fill="#7a3f2d"/>
      <path d="M66 232 C116 214 154 224 200 236 C248 216 292 214 340 232" fill="none" stroke="#4f9f72" stroke-width="11" stroke-linecap="round"/>
    `,
    schoolFair: `
      <rect x="72" y="74" width="256" height="142" rx="18" fill="#ffffff" ${commonShadow}/>
      <rect x="96" y="98" width="208" height="62" rx="10" fill="#29756f"/>
      <path d="M122 126 H178 M202 126 H280 M122 144 H238" stroke="#e8fff8" stroke-width="6" stroke-linecap="round"/>
      <path d="M88 216 H312 L286 252 H114 Z" fill="#f7c86b"/>
      <rect x="126" y="194" width="148" height="32" rx="9" fill="${accent}" ${commonShadow}/>
      <circle cx="126" cy="244" r="18" fill="#f4b18b"/>
      <circle cx="198" cy="244" r="18" fill="#f7c59f"/>
      <circle cx="272" cy="244" r="18" fill="#d99c77"/>
    `,
    nightMarket: `
      <path d="M56 112 H344 L318 176 H82 Z" fill="${accent}" ${commonShadow}/>
      <path d="M78 112 L98 74 H302 L322 112" fill="#fff0bf" stroke="#d9803f" stroke-width="6"/>
      <rect x="92" y="176" width="216" height="58" rx="12" fill="#ffe3a3" ${commonShadow}/>
      <path d="M112 198 H178 M206 198 H282 M122 218 H266" stroke="#9a5a25" stroke-width="6" stroke-linecap="round"/>
      <circle cx="92" cy="78" r="14" fill="#ffcf56"/>
      <circle cx="148" cy="64" r="14" fill="#ef6f6c"/>
      <circle cx="250" cy="64" r="14" fill="#69c0b8"/>
      <circle cx="308" cy="78" r="14" fill="#ffcf56"/>
      <path d="M62 250 C112 228 160 236 204 250 C252 230 302 230 344 250" fill="none" stroke="#6b8f71" stroke-width="10" stroke-linecap="round"/>
    `,
    dragonBoat: `
      <path d="M44 198 C110 226 266 226 356 198 C338 242 90 246 44 198 Z" fill="${accent}" ${commonShadow}/>
      <path d="M318 174 C344 166 358 178 356 198 C342 188 330 184 318 174 Z" fill="#ef6f6c"/>
      <circle cx="337" cy="184" r="5" fill="#1f2937"/>
      <path d="M88 174 L120 142 M146 174 L178 142 M204 174 L236 142 M262 174 L294 142" stroke="#7a3f2d" stroke-width="8" stroke-linecap="round"/>
      <circle cx="104" cy="162" r="17" fill="#f4b18b"/>
      <circle cx="164" cy="162" r="17" fill="#f7c59f"/>
      <circle cx="224" cy="162" r="17" fill="#d99c77"/>
      <circle cx="284" cy="162" r="17" fill="#f4b18b"/>
      <path d="M48 238 C94 224 138 250 184 236 C232 222 280 250 350 232" fill="none" stroke="#4aa3c7" stroke-width="13" stroke-linecap="round"/>
    `,
  };

  return illustrations[icon];
}

function storyImage(scene: StoryScene): string {
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="400" height="300" viewBox="0 0 400 300">
      <defs>
        <linearGradient id="sky" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stop-color="${scene.sky}"/>
          <stop offset="100%" stop-color="#fffaf0"/>
        </linearGradient>
        <filter id="softShadow" x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="0" dy="8" stdDeviation="8" flood-color="#17202a" flood-opacity="0.18"/>
        </filter>
      </defs>
      <rect width="400" height="300" rx="26" fill="url(#sky)"/>
      <path d="M0 208 C76 186 128 224 198 204 C270 184 326 190 400 166 V300 H0 Z" fill="${scene.ground}"/>
      <circle cx="331" cy="57" r="31" fill="#ffffff" opacity="0.62"/>
      <circle cx="354" cy="74" r="18" fill="#ffffff" opacity="0.35"/>
      ${sceneIllustration(scene.icon, scene.accent)}
      <rect x="24" y="220" width="352" height="56" rx="18" fill="rgba(255,255,255,0.92)" filter="url(#softShadow)"/>
      <text x="44" y="244" font-family="Inter, Arial, sans-serif" font-size="18" font-weight="800" fill="#23302f">${escapeSvgText(scene.title)}</text>
      <text x="44" y="263" font-family="Inter, Arial, sans-serif" font-size="12" font-weight="700" fill="#566260">${escapeSvgText(scene.subtitle)}</text>
    </svg>
  `;

  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

function storySequence(scenes: StoryScene[]): string[] {
  return scenes.map(storyImage);
}

const topicImages: Record<string, string[]> = {
  adventure: storySequence([
    {
      title: "Lanterns Arrive",
      subtitle: "A family enters the festival",
      sky: "#dff3ff",
      ground: "#d8ead5",
      accent: "#e85d5a",
      icon: "lantern",
    },
    {
      title: "Writing Wishes",
      subtitle: "Students choose kind words",
      sky: "#ffe7c8",
      ground: "#e6d9b8",
      accent: "#e88f3a",
      icon: "lantern",
    },
    {
      title: "A Lantern Falls",
      subtitle: "People work together",
      sky: "#dfd7ff",
      ground: "#d5cbe8",
      accent: "#7c6be8",
      icon: "lantern",
    },
    {
      title: "Lights in the Sky",
      subtitle: "Everyone shares hope",
      sky: "#fff1b8",
      ground: "#d7e8c4",
      accent: "#0f766e",
      icon: "lantern",
    },
  ]),
  nature: storySequence([
    {
      title: "Early Train",
      subtitle: "Friends meet at the station",
      sky: "#cceeff",
      ground: "#c5dfcf",
      accent: "#bd5b42",
      icon: "mountainTrain",
    },
    {
      title: "Forest Track",
      subtitle: "The train climbs Alishan",
      sky: "#cdf2df",
      ground: "#b9d9ba",
      accent: "#0f766e",
      icon: "mountainTrain",
    },
    {
      title: "Fog on the Path",
      subtitle: "The group waits calmly",
      sky: "#d9e6f2",
      ground: "#bdcdbd",
      accent: "#6f8fa0",
      icon: "mountainTrain",
    },
    {
      title: "Sunrise View",
      subtitle: "They describe the morning",
      sky: "#ffe2b8",
      ground: "#d9e7bd",
      accent: "#d98c3d",
      icon: "mountainTrain",
    },
  ]),
  fantasy: storySequence([
    {
      title: "Temple Morning",
      subtitle: "Neighbors prepare flowers",
      sky: "#fff0bf",
      ground: "#e6d7b8",
      accent: "#d9483b",
      icon: "temple",
    },
    {
      title: "Mazu Parade",
      subtitle: "The street becomes busy",
      sky: "#ffd9ca",
      ground: "#e8c9b9",
      accent: "#c2413f",
      icon: "temple",
    },
    {
      title: "Lost in the Crowd",
      subtitle: "A child asks for help",
      sky: "#d7e4ff",
      ground: "#d1d8e8",
      accent: "#5268a8",
      icon: "temple",
    },
    {
      title: "Safe Together",
      subtitle: "The community celebrates",
      sky: "#dff6e6",
      ground: "#c9e4ca",
      accent: "#2f8f68",
      icon: "temple",
    },
  ]),
  school: storySequence([
    {
      title: "Class Idea",
      subtitle: "Students plan a Taiwan fair",
      sky: "#d7efff",
      ground: "#d5e7d5",
      accent: "#0f766e",
      icon: "schoolFair",
    },
    {
      title: "Making Posters",
      subtitle: "Teams explain local foods",
      sky: "#d6f4ef",
      ground: "#cae6dc",
      accent: "#2e9384",
      icon: "schoolFair",
    },
    {
      title: "Rain at Noon",
      subtitle: "The class moves tables",
      sky: "#e5dfd1",
      ground: "#d9d0b8",
      accent: "#bf8544",
      icon: "schoolFair",
    },
    {
      title: "Sharing Culture",
      subtitle: "Visitors ask questions",
      sky: "#dff3d2",
      ground: "#cfe4bc",
      accent: "#4e9d72",
      icon: "schoolFair",
    },
  ]),
  mystery: storySequence([
    {
      title: "Night Market Snack",
      subtitle: "Friends buy bubble tea",
      sky: "#ffe5c7",
      ground: "#e3c9aa",
      accent: "#e08a45",
      icon: "nightMarket",
    },
    {
      title: "A Wallet Is Missing",
      subtitle: "They look near the stall",
      sky: "#d7d4f3",
      ground: "#c9c2db",
      accent: "#6b5dad",
      icon: "nightMarket",
    },
    {
      title: "Clue from a Vendor",
      subtitle: "The owner remembers a detail",
      sky: "#dce7ff",
      ground: "#ccd7e7",
      accent: "#536aa4",
      icon: "nightMarket",
    },
    {
      title: "Returned Wallet",
      subtitle: "Everyone says thank you",
      sky: "#d8f4e6",
      ground: "#c6e4cd",
      accent: "#2f8f68",
      icon: "nightMarket",
    },
  ]),
  "daily-life": storySequence([
    {
      title: "Dragon Boat Practice",
      subtitle: "A team meets before school",
      sky: "#cfeeff",
      ground: "#c4dfcf",
      accent: "#238d7a",
      icon: "dragonBoat",
    },
    {
      title: "Learning the Rhythm",
      subtitle: "The drummer gives a beat",
      sky: "#d6f2e4",
      ground: "#c7e5d0",
      accent: "#55a06f",
      icon: "dragonBoat",
    },
    {
      title: "Strong Wind",
      subtitle: "The boat slows down",
      sky: "#d7e2f3",
      ground: "#c8ddbe",
      accent: "#457f9a",
      icon: "dragonBoat",
    },
    {
      title: "Finish Line",
      subtitle: "The team cheers together",
      sky: "#ffd9ca",
      ground: "#e5cdbb",
      accent: "#d97854",
      icon: "dragonBoat",
    },
  ]),
};

export const TOPICS: Topic[] = [
  {
    id: "adventure",
    name: "Taiwan Lantern Festival",
    description: "Tell a story about wishes, lights, and helping others at a Taiwan festival.",
    skillFocus: "Sequence and feelings",
    level: "Culture Story",
    images: topicImages.adventure,
    vocabulary: {
      0: ["元宵", "燈籠", "家人", "人群"],
      1: ["願望", "寫字", "祝福", "開心"],
      2: ["掉下來", "幫忙", "小心", "一起"],
      3: ["天空", "發光", "希望", "分享"],
    },
  },
  {
    id: "nature",
    name: "Alishan Sunrise Train",
    description: "Describe a mountain trip in Taiwan from train station to sunrise.",
    skillFocus: "Setting and description",
    level: "Place Story",
    images: topicImages.nature,
    vocabulary: {
      0: ["火車", "車站", "朋友", "出發"],
      1: ["阿里山", "森林", "山路", "上山"],
      2: ["霧", "等待", "安靜", "冷"],
      3: ["日出", "雲海", "漂亮", "拍照"],
    },
  },
  {
    id: "fantasy",
    name: "Mazu Parade Helper",
    description: "Tell a community story about a Mazu parade and helping someone get home safely.",
    skillFocus: "Community and problem solving",
    level: "Culture Helper",
    images: topicImages.fantasy,
    vocabulary: {
      0: ["媽祖", "廟", "花", "早上"],
      1: ["遶境", "街道", "熱鬧", "隊伍"],
      2: ["迷路", "孩子", "緊張", "尋找"],
      3: ["安全", "謝謝", "平安", "回家"],
    },
  },
  {
    id: "school",
    name: "Taiwan Culture Fair",
    description: "Tell a school story where students introduce Taiwan food and places.",
    skillFocus: "Explaining and teamwork",
    level: "Class Project",
    images: topicImages.school,
    vocabulary: {
      0: ["學校", "主意", "台灣", "活動"],
      1: ["海報", "小組", "美食", "介紹"],
      2: ["下雨", "桌子", "移動", "合作"],
      3: ["文化", "客人", "問題", "分享"],
    },
  },
  {
    id: "mystery",
    name: "Night Market Lost Wallet",
    description: "Build a mystery story at a Taiwan night market using clues and kindness.",
    skillFocus: "Problem and solution",
    level: "Kindness Mystery",
    images: topicImages.mystery,
    vocabulary: {
      0: ["夜市", "珍珠奶茶", "小吃", "朋友"],
      1: ["錢包", "不見", "著急", "找"],
      2: ["老闆", "線索", "記得", "問"],
      3: ["找到", "還給", "謝謝", "誠實"],
    },
  },
  {
    id: "daily-life",
    name: "Dragon Boat Team",
    description: "Practice a sports story about teamwork during a Taiwan Dragon Boat Festival race.",
    skillFocus: "Action and encouragement",
    level: "Team Story",
    images: topicImages["daily-life"],
    vocabulary: {
      0: ["端午節", "龍舟", "隊友", "練習"],
      1: ["鼓聲", "節奏", "划船", "加油"],
      2: ["風", "慢下來", "努力", "不放棄"],
      3: ["終點", "成功", "歡呼", "團隊"],
    },
  },
];

export default function TopicSelector({ onTopicSelect }: TopicSelectorProps) {
  const [selectedTopic, setSelectedTopic] = useState<Topic>(TOPICS[0]);
  const [selectedImageIndex, setSelectedImageIndex] = useState(0);

  const selectedImage = selectedTopic.images[selectedImageIndex];
  const selectedWords = selectedTopic.vocabulary[selectedImageIndex] || [];

  const chooseTopic = (topic: Topic) => {
    setSelectedTopic(topic);
    setSelectedImageIndex(0);
  };

  return (
    <div className="topic-selector">
      <section className="learning-hero">
        <div className="learning-hero-copy">
          <p className="platform-kicker">Student narrative lab</p>
          <h1>Choose a Taiwan Story</h1>
          <p>
            Select a Taiwan event or community story, study the connected
            picture sequence, prepare useful Mandarin vocabulary, and record a
            complete spoken story for Praat prosody and Gemini language
            feedback.
          </p>
        </div>

        <div className="learning-objectives" aria-label="Learning objectives">
          <div>
            <strong>1</strong>
            <span>Plan the story</span>
          </div>
          <div>
            <strong>2</strong>
            <span>Record Mandarin speech</span>
          </div>
          <div>
            <strong>3</strong>
            <span>Review pronunciation and language feedback</span>
          </div>
        </div>
      </section>

      <section className="activity-layout">
        <aside className="activity-sidebar" aria-label="Story topics">
          <div className="sidebar-heading">
            <p className="platform-kicker">Activity menu</p>
            <h2>Taiwan story topics</h2>
          </div>

          <div className="topic-list">
            {TOPICS.map((topic) => (
              <button
                type="button"
                key={topic.id}
                className={`topic-row ${
                  selectedTopic.id === topic.id ? "selected" : ""
                }`}
                onClick={() => chooseTopic(topic)}
              >
                <span>
                  <strong>{topic.name}</strong>
                  <small>{topic.skillFocus}</small>
                </span>
                <em>{topic.level}</em>
              </button>
            ))}
          </div>
        </aside>

        <section className="activity-preview" aria-label="Selected activity">
          <div className="preview-header">
            <div>
              <p className="platform-kicker">Selected module</p>
              <h2>{selectedTopic.name}</h2>
              <p>{selectedTopic.description}</p>
            </div>
            <div className="module-badge">{selectedTopic.level}</div>
          </div>

          <div className="preview-grid">
            <div className="main-prompt-card">
              <img
                src={selectedImage}
                alt={`${selectedTopic.name} story part ${
                  selectedImageIndex + 1
                }`}
              />
              <div className="prompt-number">
                Story part {selectedImageIndex + 1} of{" "}
                {selectedTopic.images.length}
              </div>
            </div>

            <div className="prompt-planning-panel">
              <div className="planning-block">
                <h3>Speaking goals</h3>
                <ul>
                  <li>Describe the Taiwan place, event, or people clearly.</li>
                  <li>Use time words to connect events.</li>
                  <li>Finish with a result, feeling, or lesson.</li>
                </ul>
              </div>

              <div className="planning-block">
                <h3>Vocabulary support</h3>
                <div className="vocabulary-chips">
                  {selectedWords.map((word) => (
                    <span key={word}>{word}</span>
                  ))}
                </div>
              </div>

              <button
                type="button"
                className="start-activity-btn"
                onClick={() => onTopicSelect?.(selectedTopic)}
              >
                Start recording this activity
              </button>
            </div>
          </div>

          <div className="prompt-strip" aria-label="Story sequence prompts">
            {selectedTopic.images.map((image, index) => (
              <button
                type="button"
                key={image}
                className={`prompt-thumb ${
                  selectedImageIndex === index ? "active" : ""
                }`}
                onClick={() => setSelectedImageIndex(index)}
              >
                <img src={image} alt={`Story part ${index + 1}`} />
                <span>Part {index + 1}</span>
              </button>
            ))}
          </div>
        </section>
      </section>
    </div>
  );
}
