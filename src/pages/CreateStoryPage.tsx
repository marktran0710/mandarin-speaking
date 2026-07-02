import { useState } from "react";
import TopicSelector from "../components/TopicSelector";
import StoryRecorder from "../components/StoryRecorder";
import { HelpRequest } from "../services/database";
import { loadPublishedTeacherTopics } from "../utils/teacherStories";
import type { Topic } from "../components/TopicSelector";
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
      <div className="csp-help-strip">
        <StudentHelpPanel helpRequests={helpRequests} onRaiseHand={onRaiseHand} />
      </div>
      {!selectedTopic ? (
        <TopicSelector onTopicSelect={handleTopicSelect} />
      ) : (
        <div className="csp-recorder-body">
          <div className="csp-page-header">
            <button className="btn-back" onClick={handleBack}>
              ← <BiLabel k="back_to_topics" />
            </button>
            <div className="csp-breadcrumb">
              <span><BiLabel k="activity_menu" /></span>
              <span className="csp-breadcrumb-sep">›</span>
              <span className="csp-breadcrumb-active">{selectedTopic.name}</span>
            </div>
          </div>
          <StoryRecorder
            topic={selectedTopic}
            selectedImage={selectedImage}
            selectedImageIndex={selectedImageIndex}
            onImageSelect={setSelectedImageIndex}
            onImageChange={(image) => setSelectedImage(image)}
            onAddRecord={onAddRecord}
            enableSorting={false}
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
  const [message, setMessage] = useState("我的故事需要協助。");
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
              ? <BiLabel k="teacher_has_your_help_request" />
              : <BiLabel k="need_teacher_help" />}
          </strong>
          <p>
            {activeRequest
              ? <BiText k="stay_on_your_task_your_teacher_can_see_t" />
              : <BiText k="raise_your_hand_from_here_and_your_teach" />}
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
          {activeRequest ? <BiLabel k="update_request" /> : <BiLabel k="raise_hand" />}
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
