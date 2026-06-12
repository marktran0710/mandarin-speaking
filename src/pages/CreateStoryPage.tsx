import { useState } from "react";
import TopicSelector from "../TopicSelector";
import StoryRecorder from "../components/StoryRecorder";
import { HelpRequest } from "../database";
import { loadPublishedTeacherTopics } from "../utils/teacherStories";
import "./CreateStoryPage.css";

interface CreateStoryPageProps {
  onAddRecord: (record: any) => void;
  initialTopicId?: string;
  initialImageIndex?: number;
  helpRequests?: HelpRequest[];
  onRaiseHand?: (message: string) => void;
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
  helpRequests = [],
  onRaiseHand,
}: CreateStoryPageProps) {
  const topics = loadPublishedTeacherTopics();
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
      <StudentHelpPanel helpRequests={helpRequests} onRaiseHand={onRaiseHand} />
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

function StudentHelpPanel({
  helpRequests,
  onRaiseHand,
}: {
  helpRequests: HelpRequest[];
  onRaiseHand?: (message: string) => void;
}) {
  const [message, setMessage] = useState("I need help with my story.");
  const studentName = getStudentName();
  const activeRequest = helpRequests.find(
    (request) =>
      request.studentName === studentName && request.status === "open",
  );

  return (
    <section className="student-help-panel" aria-label="Ask teacher for help">
      <div>
        <span className="student-help-icon" aria-hidden="true">
          ?
        </span>
        <div>
          <strong>
            {activeRequest
              ? "Teacher has your help request"
              : "Need teacher help?"}
          </strong>
          <p>
            {activeRequest
              ? "Stay on your task. Your teacher can see this request."
              : "Raise your hand from here and your teacher will see it on the dashboard."}
          </p>
        </div>
      </div>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          onRaiseHand?.(message);
        }}
      >
        <input
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          aria-label="Help request message"
          placeholder="What do you need help with?"
        />
        <button type="submit" disabled={!onRaiseHand}>
          {activeRequest ? "Update request" : "Raise hand"}
        </button>
      </form>
    </section>
  );
}

function getStudentName() {
  try {
    const session = JSON.parse(localStorage.getItem("studentSession") || "{}");
    return typeof session.name === "string" && session.name.trim()
      ? session.name.trim()
      : "Student";
  } catch {
    return "Student";
  }
}
