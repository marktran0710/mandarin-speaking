import { useState } from "react";
import TopicSelector from "../TopicSelector";
import StoryRecorder from "../components/StoryRecorder";
import { HelpRequest } from "../database";
import { loadPublishedTeacherTopics } from "../utils/teacherStories";
import type { Topic } from "../TopicSelector";
import "./CreateStoryPage.css";
import { BiLabel, BiText } from "../components/BiLabel";
import "../components/BiLabel.css";

interface CreateStoryPageProps {
  onAddRecord: (record: any) => void;
  initialTopicId?: string;
  initialImageIndex?: number;
  helpRequests?: HelpRequest[];
  onRaiseHand?: (message: string) => void;
  publishedTopics?: Topic[];
}


export default function CreateStoryPage({
  onAddRecord,
  initialTopicId,
  initialImageIndex = 0,
  helpRequests = [],
  onRaiseHand,
  publishedTopics,
}: CreateStoryPageProps) {
  const topics = publishedTopics ?? loadPublishedTeacherTopics();
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
          <div className="btn-back-container">
            <button className="btn-back" onClick={handleBack}>
              <BiLabel zh="返回主題" en="Back to Topics" />
            </button>
          </div>
          <StoryRecorder
            topic={selectedTopic}
            selectedImage={selectedImage}
            selectedImageIndex={selectedImageIndex}
            onImageSelect={setSelectedImageIndex}
            onImageChange={(image) => setSelectedImage(image)}
            onAddRecord={onAddRecord}
            enableSorting={!selectedTopic.linear}
            studentName={getStudentName()}
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
              ? <BiLabel zh="老師已收到你的求助" en="Teacher has your help request" />
              : <BiLabel zh="需要老師協助嗎？" en="Need teacher help?" />}
          </strong>
          <p>
            {activeRequest
              ? <BiText zh="請繼續你的任務，老師已經看到這個請求。" en="Stay on your task. Your teacher can see this request." />
              : <BiText zh="點此舉手，老師會在儀表板上看到。" en="Raise your hand from here and your teacher will see it on the dashboard." />}
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
          placeholder="需要什麼幫助？ What do you need help with?"
        />
        <button type="submit" disabled={!onRaiseHand}>
          {activeRequest ? <BiLabel zh="更新請求" en="Update request" /> : <BiLabel zh="舉手" en="Raise hand" />}
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
