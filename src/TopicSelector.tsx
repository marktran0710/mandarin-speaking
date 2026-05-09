import { useState } from "react";
import "./TopicSelector.css";

interface Topic {
  id: string;
  name: string;
  description: string;
  images: string[]; // Image URLs
  vocabulary: Record<number, string[]>; // Traditional Chinese words
}

interface TopicSelectorProps {
  onTopicSelect?: (topic: Topic) => void;
}

// Chinese vocabulary for each topic and image (4 words per image) - TRADITIONAL CHINESE
const chineseVocabulary: Record<string, Record<number, string[]>> = {
  adventure: {
    0: ["冒險", "旅行", "探險", "挑戰"],
    1: ["勇敢", "發現", "遠方", "征程"],
    2: ["山峰", "神秘", "冒險家", "尋寶"],
    3: ["成功", "堅持", "夢想", "冒險"],
  },
  nature: {
    0: ["自然", "山水", "風景", "清新"],
    1: ["森林", "綠色", "草原", "生命"],
    2: ["湖泊", "天空", "白雲", "寧靜"],
    3: ["陽光", "花朵", "河流", "美麗"],
  },
  fantasy: {
    0: ["魔法", "夢想", "神秘", "王國"],
    1: ["龍", "城堡", "精靈", "魔杖"],
    2: ["幻想", "冒險", "奇蹟", "傳奇"],
    3: ["魔法師", "咒語", "寶藏", "黑暗"],
  },
  school: {
    0: ["學校", "朋友", "學習", "開心"],
    1: ["教室", "老師", "同學", "功課"],
    2: ["操場", "運動", "團隊", "快樂"],
    3: ["書本", "知識", "友誼", "成長"],
  },
  mystery: {
    0: ["秘密", "謎題", "線索", "真相"],
    1: ["偵探", "破案", "證據", "調查"],
    2: ["隱藏", "發現", "真實", "謎團"],
    3: ["答案", "推理", "解謎", "驚人"],
  },
  "daily-life": {
    0: ["生活", "日常", "家庭", "朋友"],
    1: ["早晨", "學校", "放學", "家"],
    2: ["家人", "飯菜", "笑聲", "溫暖"],
    3: ["晚上", "故事", "睡覺", "夢想"],
  },
};

// Image URLs for each topic and image - using Picsum Photos
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
    description: "Explore exciting journeys and quests",
    images: topicImages.adventure,
    vocabulary: chineseVocabulary.adventure,
  },
  {
    id: "nature",
    name: "Nature",
    description: "Discover the beauty of the natural world",
    images: topicImages.nature,
    vocabulary: chineseVocabulary.nature,
  },
  {
    id: "fantasy",
    name: "Fantasy",
    description: "Enter magical worlds and mystical realms",
    images: topicImages.fantasy,
    vocabulary: chineseVocabulary.fantasy,
  },
  {
    id: "school",
    name: "School Life",
    description: "Stories about friendships and learning",
    images: topicImages.school,
    vocabulary: chineseVocabulary.school,
  },
  {
    id: "mystery",
    name: "Mystery",
    description: "Uncover secrets and solve puzzles",
    images: topicImages.mystery,
    vocabulary: chineseVocabulary.mystery,
  },
  {
    id: "daily-life",
    name: "Daily Life",
    description: "Celebrate everyday moments and routines",
    images: topicImages["daily-life"],
    vocabulary: chineseVocabulary["daily-life"],
  },
];

export default function TopicSelector({ onTopicSelect }: TopicSelectorProps) {
  const [selectedTopic, setSelectedTopic] = useState<Topic | null>(null);
  const [selectedImageIndex, setSelectedImageIndex] = useState<number>(0);
  const [loadedImages, setLoadedImages] = useState<Set<string>>(new Set());
  const [failedImages, setFailedImages] = useState<Set<string>>(new Set());

  const handleTopicClick = (topic: Topic) => {
    setSelectedTopic(topic);
    setSelectedImageIndex(0);
  };

  const handleConfirmSelection = () => {
    if (selectedTopic) {
      onTopicSelect?.(selectedTopic);
    }
  };

  const handleImageSelect = (index: number) => {
    setSelectedImageIndex(index);
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
      {/* Hero Section */}
      <section className="hero-section">
        <div className="hero-content">
          <div className="hero-text">
            <h1 className="hero-title">Create Your Story</h1>
            <p className="hero-subtitle">
              Choose a topic and pick an image to start your storytelling
              journey
            </p>
          </div>
        </div>
      </section>

      {/* Topics Grid */}
      <section className="topics-section">
        <div className="section-container">
          <div className="topics-grid">
            {TOPICS.map((topic) => (
              <div
                key={topic.id}
                className={`topic-card ${selectedTopic?.id === topic.id ? "selected" : ""}`}
                onClick={() => handleTopicClick(topic)}
              >
                <div className="topic-preview">
                  <img
                    src={topic.images[0]}
                    alt={topic.name}
                    className="topic-image"
                    onLoad={() => handleImageLoad(topic.images[0])}
                    onError={() => handleImageError(topic.images[0])}
                  />
                  {!isImageLoaded(topic.images[0]) && !hasImageFailed(topic.images[0]) && (
                    <div className="image-loading-skeleton" />
                  )}
                  <div className="topic-overlay">
                    <div className="overlay-content">
                      <h3 className="topic-name">{topic.name}</h3>
                      <p className="topic-description">{topic.description}</p>
                      <button className="btn-select">Select Topic</button>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Detail Panel */}
      {selectedTopic && (
        <section className="detail-section">
          <div className="section-container">
            <div className="detail-header">
              <h2 className="detail-title">{selectedTopic.name}</h2>
              <p className="detail-description">{selectedTopic.description}</p>
            </div>

            {/* Image Selection Grid */}
            <div className="image-selection">
              <div className="main-image-container">
                <img
                  src={selectedTopic.images[selectedImageIndex]}
                  alt={`${selectedTopic.name} ${selectedImageIndex + 1}`}
                  className="main-image"
                  onLoad={() => handleImageLoad(selectedTopic.images[selectedImageIndex])}
                  onError={() => handleImageError(selectedTopic.images[selectedImageIndex])}
                />
                {!isImageLoaded(selectedTopic.images[selectedImageIndex]) && !hasImageFailed(selectedTopic.images[selectedImageIndex]) && (
                  <div className="image-loading-skeleton main" />
                )}
                <div className="image-counter">
                  {selectedImageIndex + 1} / {selectedTopic.images.length}
                </div>
              </div>

              <div className="image-grid">
                {selectedTopic.images.map((image, index) => (
                  <div
                    key={index}
                    className={`image-thumbnail-wrapper ${selectedImageIndex === index ? "active" : ""}`}
                  >
                    <div
                      className={`image-thumbnail`}
                      onClick={() => handleImageSelect(index)}
                    >
                      <img
                        src={image}
                        alt={`Option ${index + 1}`}
                        onLoad={() => handleImageLoad(image)}
                        onError={() => handleImageError(image)}
                      />
                      {!isImageLoaded(image) && !hasImageFailed(image) && (
                        <div className="image-loading-skeleton small" />
                      )}
                      <div className="check-mark">✓</div>
                    </div>
                    <div className="image-words">
                      {chineseVocabulary[selectedTopic.id]?.[index]?.join(" / ")}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Action Buttons */}
            <div className="action-buttons">
              <button
                className="btn btn-outlined"
                onClick={() => setSelectedTopic(null)}
              >
                Choose Different Topic
              </button>
              <button
                className="btn btn-primary"
                onClick={handleConfirmSelection}
              >
                Start Creating Story with this Image
              </button>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
