import { useEffect, useState } from "react";
import TopicSelector from "../components/TopicSelector";
import StoryRecorder, { type NewAudioRecord } from "../components/StoryRecorder";
import StoryLevelPicker from "../components/StoryLevelPicker";
import { HelpRequest } from "../services/database";
import { loadPublishedTeacherTopics, storyHasTierContent, storyToTopic } from "../utils/teacherStories";
import type { Topic } from "../components/TopicSelector";
import "./CreateStoryPage.css";
import { BiLabel, BiText } from "../components/BiLabel";
import "../components/BiLabel.css";

interface CreateStoryPageProps {
  onAddRecord: (record: NewAudioRecord) => void;
  initialTopicId?: string;
  initialImageIndex?: number;
  helpRequests?: HelpRequest[];
  onRaiseHand?: (message: string) => void;
  publishedTopics?: Topic[];
  /** Fires whenever a topic practice session starts/ends, so the app shell
   * can shrink its top navbar while the student is mid-session instead of
   * stacking a full tab bar above the story's own nav panel. */
  onSessionActiveChange?: (active: boolean) => void;
}


export default function CreateStoryPage({
  onAddRecord,
  initialTopicId,
  initialImageIndex = 0,
  helpRequests = [],
  onRaiseHand,
  publishedTopics,
  onSessionActiveChange,
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
  // Set while a story with authored Medium/Hard tiers is chosen but before a
  // level has been picked — shows StoryLevelPicker instead of jumping
  // straight into StoryRecorder. Stories with no Medium/Hard content skip
  // this step entirely (nothing to choose between).
  const [pendingTopic, setPendingTopic] = useState<Topic | null>(null);

  useEffect(() => {
    onSessionActiveChange?.(Boolean(selectedTopic) || Boolean(pendingTopic));
    return () => onSessionActiveChange?.(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTopic, pendingTopic]);

  const openTopicAtLevel = (topic: Topic) => {
    setSelectedTopic(topic);
    setSelectedImage(topic.images[0]);
    setSelectedImageIndex(0);
  };

  const handleTopicSelect = (topic: Topic) => {
    const story = topic.sourceStory;
    const hasTiers =
      story && (storyHasTierContent(story, "medium") || storyHasTierContent(story, "hard"));
    if (hasTiers) {
      setPendingTopic(topic);
      return;
    }
    openTopicAtLevel(topic);
  };

  const handleBack = () => {
    setSelectedTopic(null);
    setPendingTopic(null);
    setSelectedImage("");
    setSelectedImageIndex(0);
  };

  return (
    <div className="create-story-page">
      <div className="csp-help-strip">
        <StudentHelpPanel helpRequests={helpRequests} onRaiseHand={onRaiseHand} />
      </div>
      {pendingTopic && pendingTopic.sourceStory ? (
        <StoryLevelPicker
          story={pendingTopic.sourceStory}
          onBack={() => setPendingTopic(null)}
          onSelectLevel={(level) => {
            const story = pendingTopic.sourceStory!;
            openTopicAtLevel(storyToTopic(story, level));
            setPendingTopic(null);
          }}
        />
      ) : !selectedTopic ? (
        <TopicSelector onTopicSelect={handleTopicSelect} />
      ) : (
        <div className="csp-recorder-body">
          <StoryRecorder
            topic={selectedTopic}
            selectedImage={selectedImage}
            selectedImageIndex={selectedImageIndex}
            onImageSelect={setSelectedImageIndex}
            onImageChange={(image) => setSelectedImage(image)}
            onAddRecord={onAddRecord}
            enableSorting={false}
            enableOverview={true}
            studentName={getStudentName()}
            studentId={getStudentId()}
            onExit={handleBack}
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
          {activeRequest ? (
            <>
              <strong>
                <BiLabel k="teacher_has_your_help_request" />
              </strong>
              <p>
                <BiText k="stay_on_your_task_your_teacher_can_see_t" />
              </p>
            </>
          ) : (
            <p>
              <BiText k="need_teacher_help_prompt" />
            </p>
          )}
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

// The roster-assigned id (see LoginPage), when the student signed in via
// the roster picker rather than a name typed before the roster existed.
function getStudentId(): string | undefined {
  try {
    const session = JSON.parse(localStorage.getItem("studentSession") || "{}");
    return typeof session.id === "string" && session.id ? session.id : undefined;
  } catch {
    return undefined;
  }
}
