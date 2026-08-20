import { useEffect, useState } from "react";
import TopicSelector from "../components/TopicSelector";
import StoryRecorder, { type NewAudioRecord } from "../components/StoryRecorder";
import StudentHelpPanel from "../components/StudentHelpPanel";
import { HelpRequest } from "../services/database";
import { loadPublishedTeacherTopics, storyToTopic } from "../utils/teacherStories";
import type { Topic } from "../components/TopicSelector";
import { getStudentId, getStudentName } from "../utils/studentSession";
import "./CreateStoryPage.css";
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
  useEffect(() => {
    onSessionActiveChange?.(Boolean(selectedTopic));
    return () => onSessionActiveChange?.(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTopic]);

  // `selectedTopic` is only otherwise set once, when the student opens a
  // story. If a teacher republishes that same story (same id, new script)
  // while the session stays open, `publishedTopics` refreshes from the
  // backend but this state never re-read it — the student kept practicing
  // whatever vocabulary/scenes were loaded at open time. Re-sync by id
  // whenever the backend-sourced topic list changes.
  //
  // `publishedTopics` gets a new array (and new Topic objects) on every
  // refresh even when nothing actually changed (e.g. the tab regaining
  // focus after a file-upload dialog closes) — `loadPublishedTeacherTopics`
  // re-parses from storage rather than returning a cached reference. Compare
  // by content, not by reference: replacing `selectedTopic` with an
  // unchanged-but-new object still changes `topic.images` identity downstream
  // in StoryRecorder, which resets the practice phase back to the overview
  // step — a real regression, not just a wasted render.
  useEffect(() => {
    if (!publishedTopics || !selectedTopic) return;
    const fresh = publishedTopics.find((topic) => topic.id === selectedTopic.id);
    if (!fresh || fresh === selectedTopic) return;
    if (JSON.stringify(fresh) === JSON.stringify(selectedTopic)) return;
    setSelectedTopic(fresh);
    setSelectedImageIndex((index) => {
      const clamped = Math.min(index, Math.max(fresh.images.length - 1, 0));
      setSelectedImage(fresh.images[clamped] || "");
      return clamped;
    });
  }, [publishedTopics, selectedTopic]);

  const openTopicAtLevel = (topic: Topic) => {
    setSelectedTopic(topic);
    setSelectedImage(topic.images[0]);
    setSelectedImageIndex(0);
  };

  const handleTopicSelect = (topic: Topic) => {
    openTopicAtLevel(topic);
  };

  const handleLevelSelect = (topic: Topic, level: Parameters<typeof storyToTopic>[1]) => {
    if (!topic.sourceStory) return;
    openTopicAtLevel(storyToTopic(topic.sourceStory, level, "approved"));
  };

  const handleBack = () => {
    setSelectedTopic(null);
    setSelectedImage("");
    setSelectedImageIndex(0);
  };

  return (
    <div className="create-story-page">
      {/* Outside a session the raise-hand panel is a banner strip; during a
          session it lives at the bottom of the story sidebar instead. */}
      {!selectedTopic && (
        <div className="csp-help-strip">
          <StudentHelpPanel
            helpRequests={helpRequests}
            onRaiseHand={onRaiseHand}
          />
        </div>
      )}
      {!selectedTopic ? (
        <TopicSelector onTopicSelect={handleTopicSelect} onLevelSelect={handleLevelSelect} />
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
            helpRequests={helpRequests}
            onRaiseHand={onRaiseHand}
          />
        </div>
      )}
    </div>
  );
}

