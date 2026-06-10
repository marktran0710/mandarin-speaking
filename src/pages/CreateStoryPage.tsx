import { useState } from "react";
import TopicSelector, { TOPICS } from "../TopicSelector";
import StoryRecorder from "../components/StoryRecorder";
import { loadPublishedTeacherTopics } from "../utils/teacherStories";
import "./CreateStoryPage.css";

interface CreateStoryPageProps {
  onAddRecord: (record: any) => void;
  initialTopicId?: string;
  initialImageIndex?: number;
}

interface Topic {
  id: string;
  name: string;
  description: string;
  images: string[];
  vocabulary: Record<number, string[]>;
}

export default function CreateStoryPage({
  onAddRecord,
  initialTopicId,
  initialImageIndex = 0,
}: CreateStoryPageProps) {
  const topics = [...TOPICS, ...loadPublishedTeacherTopics()];
  const initialTopic =
    topics.find((topic) => topic.id === initialTopicId) || null;
  const safeInitialIndex = initialTopic
    ? Math.min(initialImageIndex, initialTopic.images.length - 1)
    : 0;
  const [selectedTopic, setSelectedTopic] = useState<Topic | null>(
    initialTopic,
  );
  const [selectedImage, setSelectedImage] = useState<string>(
    initialTopic?.images[safeInitialIndex] || "",
  );
  const [selectedImageIndex, setSelectedImageIndex] =
    useState<number>(safeInitialIndex);

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
            Back to Topics
          </button>
          <StoryRecorder
            topic={selectedTopic}
            selectedImage={selectedImage}
            selectedImageIndex={selectedImageIndex}
            onImageSelect={setSelectedImageIndex}
            onImageChange={(image) => setSelectedImage(image)}
            onAddRecord={onAddRecord}
          />
        </div>
      )}
    </div>
  );
}
