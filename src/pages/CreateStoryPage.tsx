import { useState } from "react";
import TopicSelector from "../TopicSelector";
import StoryRecorder from "../components/StoryRecorder";
import "./CreateStoryPage.css";

interface CreateStoryPageProps {
  onAddRecord: (record: any) => void;
}

interface Topic {
  id: string;
  name: string;
  description: string;
  images: string[];
  vocabulary: Record<number, string[]>;
}

export default function CreateStoryPage({ onAddRecord }: CreateStoryPageProps) {
  const [selectedTopic, setSelectedTopic] = useState<Topic | null>(null);
  const [selectedImage, setSelectedImage] = useState<string>("");
  const [selectedImageIndex, setSelectedImageIndex] = useState<number>(0);

  const handleTopicSelect = (topic: Topic) => {
    setSelectedTopic(topic);
    setSelectedImage(topic.images[0]);
    setSelectedImageIndex(0);
  };

  const handleBack = () => {
    setSelectedTopic(null);
    setSelectedImage("");
    setSelectedImageIndex(0);
  };

  return (
    <div className="create-story-page">
      {!selectedTopic ? (
        <TopicSelector onTopicSelect={handleTopicSelect} />
      ) : (
        <div className="story-recorder-wrapper">
          <button className="btn-back" onClick={handleBack}>
            ← Back to Topics
          </button>
          <StoryRecorder
            topic={selectedTopic}
            selectedImage={selectedImage}
            selectedImageIndex={selectedImageIndex}
            onImageSelect={setSelectedImageIndex}
            onImageChange={(img) => setSelectedImage(img)}
            onAddRecord={onAddRecord}
          />
        </div>
      )}
    </div>
  );
}
