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

const topicImages: Record<string, string[]> = {
  adventure: [
    "https://picsum.photos/400/300?random=1",
    "https://picsum.photos/400/300?random=2",
    "https://picsum.photos/400/300?random=3",
    "https://picsum.photos/400/300?random=4",
  ],
  nature: [
    "https://picsum.photos/400/300?random=5",
    "https://picsum.photos/400/300?random=6",
    "https://picsum.photos/400/300?random=7",
    "https://picsum.photos/400/300?random=8",
  ],
  fantasy: [
    "https://picsum.photos/400/300?random=9",
    "https://picsum.photos/400/300?random=10",
    "https://picsum.photos/400/300?random=11",
    "https://picsum.photos/400/300?random=12",
  ],
  school: [
    "https://picsum.photos/400/300?random=13",
    "https://picsum.photos/400/300?random=14",
    "https://picsum.photos/400/300?random=15",
    "https://picsum.photos/400/300?random=16",
  ],
  mystery: [
    "https://picsum.photos/400/300?random=17",
    "https://picsum.photos/400/300?random=18",
    "https://picsum.photos/400/300?random=19",
    "https://picsum.photos/400/300?random=20",
  ],
  "daily-life": [
    "https://picsum.photos/400/300?random=21",
    "https://picsum.photos/400/300?random=22",
    "https://picsum.photos/400/300?random=23",
    "https://picsum.photos/400/300?random=24",
  ],
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
      0: ["冒險", "旅行", "挑戰", "發現"],
      1: ["勇敢", "山峰", "遠方", "探索"],
      2: ["森林", "尋找", "秘密", "地圖"],
      3: ["成功", "朋友", "夢想", "故事"],
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
      0: ["自然", "山水", "風景", "清新"],
      1: ["森林", "綠色", "生命", "安靜"],
      2: ["湖泊", "天空", "白雲", "陽光"],
      3: ["花朵", "河流", "美麗", "放鬆"],
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
      0: ["魔法", "夢想", "神秘", "王國"],
      1: ["城堡", "精靈", "寶藏", "傳說"],
      2: ["幻想", "奇蹟", "勇者", "旅程"],
      3: ["魔法師", "咒語", "光明", "黑暗"],
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
      0: ["學校", "朋友", "學習", "開心"],
      1: ["教室", "老師", "同學", "功課"],
      2: ["操場", "運動", "團隊", "快樂"],
      3: ["書本", "知識", "友誼", "成長"],
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
      0: ["秘密", "謎題", "線索", "真相"],
      1: ["偵探", "調查", "證據", "推理"],
      2: ["隱藏", "發現", "答案", "驚訝"],
      3: ["故事", "問題", "解決", "結果"],
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
      0: ["生活", "日常", "家庭", "朋友"],
      1: ["早晨", "學校", "放學", "回家"],
      2: ["家人", "飯菜", "笑聲", "溫暖"],
      3: ["晚上", "故事", "睡覺", "夢想"],
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
            Select a topic, study the picture prompt, prepare useful Mandarin
            vocabulary, and record a complete spoken story for Praat prosody and
            Gemini language feedback.
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
                alt={`${selectedTopic.name} prompt ${selectedImageIndex + 1}`}
              />
              <div className="prompt-number">
                Prompt {selectedImageIndex + 1} of {selectedTopic.images.length}
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

          <div className="prompt-strip" aria-label="Picture prompts">
            {selectedTopic.images.map((image, index) => (
              <button
                type="button"
                key={image}
                className={`prompt-thumb ${
                  selectedImageIndex === index ? "active" : ""
                }`}
                onClick={() => setSelectedImageIndex(index)}
              >
                <img src={image} alt={`Prompt ${index + 1}`} />
                <span>Picture {index + 1}</span>
              </button>
            ))}
          </div>
        </section>
      </section>
    </div>
  );
}
