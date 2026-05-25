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
  | "adventure"
  | "nature"
  | "fantasy"
  | "school"
  | "mystery"
  | "daily";

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
    adventure: `
      <path d="M38 208 C106 154 155 255 220 180 C273 118 326 185 378 126" fill="none" stroke="${accent}" stroke-width="14" stroke-linecap="round" opacity="0.65"/>
      <path d="M70 194 L126 108 L178 194 Z" fill="#5b8c76" ${commonShadow}/>
      <path d="M120 194 L206 74 L294 194 Z" fill="#497d6f" ${commonShadow}/>
      <path d="M172 122 L206 74 L242 124 C221 112 201 111 172 122 Z" fill="#f7fafc"/>
      <rect x="62" y="58" width="86" height="58" rx="10" fill="#fff7df" ${commonShadow}/>
      <path d="M78 74 C98 88 111 54 134 82" fill="none" stroke="#d88b3d" stroke-width="5" stroke-linecap="round"/>
      <circle cx="101" cy="92" r="6" fill="${accent}"/>
    `,
    nature: `
      <circle cx="310" cy="74" r="32" fill="#ffd166" opacity="0.95"/>
      <path d="M34 182 C88 118 138 216 194 146 C240 91 300 163 366 106" fill="none" stroke="#8fd6c2" stroke-width="18" stroke-linecap="round"/>
      <rect x="94" y="135" width="20" height="72" rx="9" fill="#8b5e3c"/>
      <circle cx="84" cy="129" r="36" fill="#4f9f72" ${commonShadow}/>
      <circle cx="119" cy="116" r="42" fill="#63b97d" ${commonShadow}/>
      <circle cx="147" cy="141" r="32" fill="#3f8f68" ${commonShadow}/>
      <path d="M230 96 C251 66 289 68 306 101 C333 102 346 122 336 144 L218 144 C203 121 211 101 230 96 Z" fill="#ffffff" opacity="0.88" ${commonShadow}/>
    `,
    fantasy: `
      <path d="M122 202 L122 108 L146 108 L146 84 L174 84 L174 108 L226 108 L226 84 L254 84 L254 108 L278 108 L278 202 Z" fill="#8b7bd8" ${commonShadow}/>
      <path d="M154 202 L154 136 C154 116 176 103 200 103 C224 103 246 116 246 136 L246 202 Z" fill="#6757b8"/>
      <path d="M132 84 L146 56 L160 84 Z M212 84 L226 56 L240 84 Z" fill="#f6c453"/>
      <circle cx="206" cy="72" r="15" fill="${accent}" opacity="0.85"/>
      <path d="M316 68 L324 88 L345 91 L329 105 L334 126 L316 115 L298 126 L303 105 L287 91 L308 88 Z" fill="#fff3b0" ${commonShadow}/>
      <path d="M70 140 C82 118 112 118 124 140 C112 163 82 163 70 140 Z" fill="#c8bfff" opacity="0.8"/>
    `,
    school: `
      <rect x="74" y="70" width="252" height="134" rx="18" fill="#ffffff" ${commonShadow}/>
      <rect x="98" y="94" width="204" height="74" rx="8" fill="#29756f"/>
      <path d="M120 126 L164 126 M120 146 L206 146 M224 126 L282 126" stroke="#e8fff8" stroke-width="6" stroke-linecap="round"/>
      <rect x="126" y="188" width="148" height="16" rx="8" fill="#e5b36a"/>
      <circle cx="116" cy="222" r="22" fill="#f4b18b"/>
      <circle cx="198" cy="222" r="22" fill="#f7c59f"/>
      <circle cx="280" cy="222" r="22" fill="#d99c77"/>
      <path d="M89 251 C96 232 136 232 143 251 M171 251 C178 232 218 232 225 251 M253 251 C260 232 300 232 307 251" fill="${accent}" opacity="0.72"/>
    `,
    mystery: `
      <rect x="86" y="88" width="186" height="118" rx="16" fill="#fff9e8" ${commonShadow}/>
      <path d="M106 116 L252 116 M106 144 L226 144 M106 172 L206 172" stroke="#947a55" stroke-width="7" stroke-linecap="round"/>
      <circle cx="264" cy="148" r="47" fill="none" stroke="${accent}" stroke-width="16" ${commonShadow}/>
      <path d="M296 181 L346 231" stroke="${accent}" stroke-width="17" stroke-linecap="round"/>
      <path d="M74 214 C98 203 118 203 141 214 M58 238 C91 224 121 224 154 238" fill="none" stroke="#6e7d9b" stroke-width="6" stroke-linecap="round" opacity="0.6"/>
    `,
    daily: `
      <path d="M78 164 L198 72 L322 164 V232 H78 Z" fill="#9cc7bf" ${commonShadow}/>
      <path d="M54 168 L198 58 L346 168" fill="none" stroke="${accent}" stroke-width="20" stroke-linecap="round" stroke-linejoin="round"/>
      <rect x="154" y="168" width="54" height="64" rx="8" fill="#fff7df"/>
      <rect x="232" y="176" width="52" height="42" rx="8" fill="#f7fbff"/>
      <path d="M238 197 H278 M258 180 V216" stroke="#74a9a0" stroke-width="5"/>
      <circle cx="92" cy="72" r="28" fill="#ffd166" opacity="0.95"/>
      <path d="M102 246 C144 224 254 224 296 246" fill="none" stroke="#6b8f71" stroke-width="12" stroke-linecap="round"/>
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
      <path d="M0 206 C72 184 118 222 190 202 C262 181 320 188 400 164 V300 H0 Z" fill="${scene.ground}"/>
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
      title: "Packing for the Trip",
      subtitle: "The friends find a map",
      sky: "#c8f1ff",
      ground: "#d7efce",
      accent: "#0f766e",
      icon: "adventure",
    },
    {
      title: "Crossing the Forest",
      subtitle: "They follow the trail",
      sky: "#bfead4",
      ground: "#b7dfbc",
      accent: "#2f8f68",
      icon: "adventure",
    },
    {
      title: "The Bridge Breaks",
      subtitle: "A challenge appears",
      sky: "#d9e6ff",
      ground: "#cbd7b8",
      accent: "#6d8cc7",
      icon: "adventure",
    },
    {
      title: "Finding the Lookout",
      subtitle: "They celebrate together",
      sky: "#ffe6ba",
      ground: "#d8e8bf",
      accent: "#e5983f",
      icon: "adventure",
    },
  ]),
  nature: storySequence([
    {
      title: "Morning at the Park",
      subtitle: "The class observes the sky",
      sky: "#ccf5e7",
      ground: "#bee8c9",
      accent: "#34a37a",
      icon: "nature",
    },
    {
      title: "Clouds Gather",
      subtitle: "Wind changes the plan",
      sky: "#d7e2f3",
      ground: "#c8ddbe",
      accent: "#6d8ca8",
      icon: "nature",
    },
    {
      title: "Rain Changes Everything",
      subtitle: "They wait and notice details",
      sky: "#c8d7ec",
      ground: "#a9ccb8",
      accent: "#457f9a",
      icon: "nature",
    },
    {
      title: "Rainbow After Rain",
      subtitle: "The group shares discoveries",
      sky: "#ffe0cb",
      ground: "#c9e6bd",
      accent: "#f28b82",
      icon: "nature",
    },
  ]),
  fantasy: storySequence([
    {
      title: "A Glowing Door",
      subtitle: "A secret world opens",
      sky: "#e8d7ff",
      ground: "#ded0f0",
      accent: "#7c6be8",
      icon: "fantasy",
    },
    {
      title: "Inside the Castle",
      subtitle: "A helper gives a clue",
      sky: "#d8e0ff",
      ground: "#d2c3ea",
      accent: "#6d5bd2",
      icon: "fantasy",
    },
    {
      title: "The Lost Crown",
      subtitle: "The hero must decide",
      sky: "#f2d6e9",
      ground: "#cdbfe3",
      accent: "#c95b8f",
      icon: "fantasy",
    },
    {
      title: "Magic Returns",
      subtitle: "Peace comes back",
      sky: "#fff0bb",
      ground: "#d6e5c3",
      accent: "#d6a23f",
      icon: "fantasy",
    },
  ]),
  school: storySequence([
    {
      title: "Before Class",
      subtitle: "Students receive a project",
      sky: "#d7efff",
      ground: "#d5e7d5",
      accent: "#0f766e",
      icon: "school",
    },
    {
      title: "Group Planning",
      subtitle: "Everyone shares ideas",
      sky: "#d6f4ef",
      ground: "#cae6dc",
      accent: "#2e9384",
      icon: "school",
    },
    {
      title: "Practice Mistake",
      subtitle: "The team fixes the poster",
      sky: "#f0e3ca",
      ground: "#dfd8bc",
      accent: "#bf8544",
      icon: "school",
    },
    {
      title: "Presentation Success",
      subtitle: "The class gives feedback",
      sky: "#dff3d2",
      ground: "#cfe4bc",
      accent: "#4e9d72",
      icon: "school",
    },
  ]),
  mystery: storySequence([
    {
      title: "Missing Notebook",
      subtitle: "A strange clue appears",
      sky: "#dce7ff",
      ground: "#ced5e4",
      accent: "#536aa4",
      icon: "mystery",
    },
    {
      title: "Clues in the Hallway",
      subtitle: "The students compare evidence",
      sky: "#e6dfd3",
      ground: "#d1c4ad",
      accent: "#7e6f58",
      icon: "mystery",
    },
    {
      title: "A Hidden Message",
      subtitle: "The answer is almost clear",
      sky: "#d7d4f3",
      ground: "#c3bed8",
      accent: "#6b5dad",
      icon: "mystery",
    },
    {
      title: "The Truth",
      subtitle: "The problem is solved",
      sky: "#d8f4e6",
      ground: "#c6e4cd",
      accent: "#2f8f68",
      icon: "mystery",
    },
  ]),
  "daily-life": storySequence([
    {
      title: "Breakfast at Home",
      subtitle: "The day begins with family",
      sky: "#fff0bf",
      ground: "#e7d7b6",
      accent: "#d79a3a",
      icon: "daily",
    },
    {
      title: "On the Way to School",
      subtitle: "A friend joins the walk",
      sky: "#cfeeff",
      ground: "#c4dfcf",
      accent: "#238d7a",
      icon: "daily",
    },
    {
      title: "Helping After Class",
      subtitle: "Someone needs support",
      sky: "#d6f2e4",
      ground: "#c7e5d0",
      accent: "#55a06f",
      icon: "daily",
    },
    {
      title: "Dinner Story",
      subtitle: "The family talks together",
      sky: "#ffd9ca",
      ground: "#e5cdbb",
      accent: "#d97854",
      icon: "daily",
    },
  ]),
};

export const TOPICS: Topic[] = [
  {
    id: "adventure",
    name: "Adventure",
    description: "Describe a journey with a clear beginning, challenge, and result.",
    skillFocus: "Sequence and cause-effect",
    level: "Story Builder",
    images: topicImages.adventure,
    vocabulary: {
      0: ["地圖", "旅行", "朋友", "出發"],
      1: ["森林", "小路", "橋", "跟著"],
      2: ["問題", "害怕", "想辦法", "幫忙"],
      3: ["找到", "成功", "開心", "回家"],
    },
  },
  {
    id: "nature",
    name: "Nature",
    description: "Describe places, weather, and changes in the environment.",
    skillFocus: "Description and detail",
    level: "Scene Builder",
    images: topicImages.nature,
    vocabulary: {
      0: ["早上", "公園", "天空", "散步"],
      1: ["雲", "風", "下雨", "躲雨"],
      2: ["雨停", "彩虹", "花草", "新鮮"],
      3: ["回家", "分享", "照片", "心情"],
    },
  },
  {
    id: "fantasy",
    name: "Fantasy",
    description: "Create an imaginative story with characters, conflict, and resolution.",
    skillFocus: "Creative narration",
    level: "Imagination Lab",
    images: topicImages.fantasy,
    vocabulary: {
      0: ["魔法", "門", "光", "好奇"],
      1: ["城堡", "國王", "精靈", "秘密"],
      2: ["皇冠", "黑影", "勇敢", "保護"],
      3: ["祝福", "和平", "朋友", "回來"],
    },
  },
  {
    id: "school",
    name: "School Life",
    description: "Tell a realistic story about classmates, learning, and routines.",
    skillFocus: "Personal experience",
    level: "Daily Narrator",
    images: topicImages.school,
    vocabulary: {
      0: ["教室", "同學", "老師", "早上"],
      1: ["小組", "討論", "海報", "練習"],
      2: ["忘記", "緊張", "幫助", "修改"],
      3: ["報告", "掌聲", "成功", "學到"],
    },
  },
  {
    id: "mystery",
    name: "Mystery",
    description: "Build suspense with clues, questions, discovery, and explanation.",
    skillFocus: "Problem and solution",
    level: "Logic Story",
    images: topicImages.mystery,
    vocabulary: {
      0: ["筆記本", "不見", "奇怪", "線索"],
      1: ["走廊", "腳印", "問題", "尋找"],
      2: ["紙條", "秘密", "發現", "推理"],
      3: ["真相", "原來", "道歉", "解決"],
    },
  },
  {
    id: "daily-life",
    name: "Daily Life",
    description: "Practice clear narration about ordinary moments and family life.",
    skillFocus: "Fluency and coherence",
    level: "Conversation Ready",
    images: topicImages["daily-life"],
    vocabulary: {
      0: ["早餐", "家人", "早上", "準備"],
      1: ["上學", "公車", "朋友", "聊天"],
      2: ["幫忙", "作業", "放學", "一起"],
      3: ["晚餐", "分享", "故事", "睡覺"],
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
          <h1>Choose a Story Activity</h1>
          <p>
            Select a topic, study the connected story sequence, prepare useful
            Mandarin vocabulary, and record a complete spoken story for Praat
            prosody and Gemini language feedback.
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
            <h2>Story topics</h2>
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
                  <li>Describe the setting and people clearly.</li>
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
