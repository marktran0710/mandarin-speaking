import { useState } from "react";
import "./TopicSelector.css";

interface Topic {
  id: string;
  name: string;
  description: string;
  images: string[];
  vocabulary: Record<number, string[]>;
}

interface TopicSelectorProps {
  onTopicSelect?: (topic: Topic) => void;
}

const chineseVocabulary: Record<string, Record<number, string[]>> = {
  adventure: {
    0: ["冒險", "旅行", "挑戰", "發現"],
    1: ["勇敢", "山峰", "遠方", "探索"],
    2: ["森林", "尋找", "秘密", "地圖"],
    3: ["成功", "朋友", "夢想", "故事"],
  },
  nature: {
    0: ["自然", "山水", "風景", "清新"],
    1: ["森林", "綠色", "生命", "安靜"],
    2: ["湖泊", "天空", "白雲", "陽光"],
    3: ["花朵", "河流", "美麗", "放鬆"],
  },
  fantasy: {
    0: ["魔法", "夢想", "神秘", "王國"],
    1: ["城堡", "精靈", "寶藏", "傳說"],
    2: ["幻想", "奇蹟", "勇者", "旅程"],
    3: ["魔法師", "咒語", "光明", "黑暗"],
  },
  school: {
    0: ["學校", "朋友", "學習", "開心"],
    1: ["教室", "老師", "同學", "功課"],
    2: ["操場", "運動", "團隊", "快樂"],
    3: ["書本", "知識", "友誼", "成長"],
  },
  mystery: {
    0: ["秘密", "謎題", "線索", "真相"],
    1: ["偵探", "調查", "證據", "推理"],
    2: ["隱藏", "發現", "答案", "驚訝"],
    3: ["故事", "問題", "解決", "結果"],
  },
  "daily-life": {
    0: ["生活", "日常", "家庭", "朋友"],
    1: ["早晨", "學校", "放學", "回家"],
    2: ["家人", "飯菜", "笑聲", "溫暖"],
    3: ["晚上", "故事", "睡覺", "夢想"],
  },
};

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

const TOPICS: Topic[] = [
  {
    id: "adventure",
    name: "Adventure",
    description: "Explore journeys, discoveries, and challenges",
    images: topicImages.adventure,
    vocabulary: chineseVocabulary.adventure,
  },
  {
    id: "nature",
    name: "Nature",
    description: "Describe landscapes, weather, and quiet scenes",
    images: topicImages.nature,
    vocabulary: chineseVocabulary.nature,
  },
  {
    id: "fantasy",
    name: "Fantasy",
    description: "Tell stories about magic, kingdoms, and imagination",
    images: topicImages.fantasy,
    vocabulary: chineseVocabulary.fantasy,
  },
  {
    id: "school",
    name: "School Life",
    description: "Practice stories about classmates and learning",
    images: topicImages.school,
    vocabulary: chineseVocabulary.school,
  },
  {
    id: "mystery",
    name: "Mystery",
    description: "Build suspense with clues, questions, and answers",
    images: topicImages.mystery,
    vocabulary: chineseVocabulary.mystery,
  },
  {
    id: "daily-life",
    name: "Daily Life",
    description: "Narrate routines, family moments, and simple events",
    images: topicImages["daily-life"],
    vocabulary: chineseVocabulary["daily-life"],
  },
];

export default function TopicSelector({ onTopicSelect }: TopicSelectorProps) {
  const [selectedTopic, setSelectedTopic] = useState<Topic | null>(null);
  const [selectedImageIndex, setSelectedImageIndex] = useState(0);
  const [loadedImages, setLoadedImages] = useState<Set<string>>(new Set());
  const [failedImages, setFailedImages] = useState<Set<string>>(new Set());

  const activeTopic = selectedTopic || TOPICS[0];

  const handleConfirmSelection = () => {
    if (selectedTopic) {
      onTopicSelect?.(selectedTopic);
    }
  };

  const handleImageLoad = (imageUrl: string) => {
    setLoadedImages((prev) => new Set([...prev, imageUrl]));
  };

  const handleImageError = (imageUrl: string) => {
    setFailedImages((prev) => new Set([...prev, imageUrl]));
  };

  const isImageLoaded = (imageUrl: string) => loadedImages.has(imageUrl);
  const hasImageFailed = (imageUrl: string) => failedImages.has(imageUrl);

  return (
    <div className="topic-selector">
      <section className="hero-section">
        <div className="hero-content">
          <div className="hero-text">
            <p className="platform-kicker">Student Portal</p>
            <h1 className="hero-title">Narrative Training Activity</h1>
            <p className="hero-subtitle">
              Choose a prompt, prepare useful vocabulary, then record your
              Mandarin story for Praat and AI feedback.
            </p>
          </div>
        </div>
      </section>

      <section className="topics-section">
        <div className="section-container">
          <div className="topics-grid">
            {TOPICS.map((topic) => (
              <button
                type="button"
                key={topic.id}
                className={`topic-card ${selectedTopic?.id === topic.id ? "selected" : ""}`}
                onClick={() => {
                  setSelectedTopic(topic);
                  setSelectedImageIndex(0);
                }}
              >
                <span className="topic-name">{topic.name}</span>
                <span className="topic-description">{topic.description}</span>
              </button>
            ))}
          </div>
        </div>
      </section>

      {selectedTopic && (
        <section className="detail-section">
          <div className="section-container">
            <div className="detail-header">
              <p className="platform-kicker">Selected activity</p>
              <h2 className="detail-title">{activeTopic.name}</h2>
              <p className="detail-description">{activeTopic.description}</p>
            </div>

            <div className="image-selection">
              <div className="main-image-container">
                <img
                  src={activeTopic.images[selectedImageIndex]}
                  alt={`${activeTopic.name} prompt ${selectedImageIndex + 1}`}
                  className="main-image"
                  onLoad={() => handleImageLoad(activeTopic.images[selectedImageIndex])}
                  onError={() => handleImageError(activeTopic.images[selectedImageIndex])}
                />
                {!isImageLoaded(activeTopic.images[selectedImageIndex]) &&
                  !hasImageFailed(activeTopic.images[selectedImageIndex]) && (
                    <div className="image-loading-skeleton main" />
                  )}
                <div className="image-counter">
                  {selectedImageIndex + 1} / {activeTopic.images.length}
                </div>
              </div>

              <div className="image-grid">
                {activeTopic.images.map((image, index) => (
                  <button
                    type="button"
                    key={image}
                    className={`image-thumbnail-wrapper ${selectedImageIndex === index ? "active" : ""}`}
                    onClick={() => setSelectedImageIndex(index)}
                  >
                    <span className="image-thumbnail">
                      <img
                        src={image}
                        alt={`Prompt option ${index + 1}`}
                        onLoad={() => handleImageLoad(image)}
                        onError={() => handleImageError(image)}
                      />
                      {!isImageLoaded(image) && !hasImageFailed(image) && (
                        <span className="image-loading-skeleton small" />
                      )}
                    </span>
                    <span className="image-words">
                      {activeTopic.vocabulary[index]?.join(" / ")}
                    </span>
                  </button>
                ))}
              </div>
            </div>

            <div className="action-buttons">
              <button
                type="button"
                className="btn btn-outlined"
                onClick={() => setSelectedTopic(null)}
              >
                Choose Different Topic
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleConfirmSelection}
              >
                Start Training Activity
              </button>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
