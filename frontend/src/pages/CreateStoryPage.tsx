import { useEffect, useState } from "react";
import TopicSelector, { type TopicStartOptions } from "../components/TopicSelector";
import StoryRecorder, { type NewAudioRecord } from "../components/StoryRecorder";
import { HelpRequest } from "../services/database";
import { loadPublishedTeacherTopics, storyToTopic } from "../utils/teacherStories";
import type { Topic } from "../components/TopicSelector";
import { getStudentId, getStudentName } from "../utils/studentSession";
import { isStoryLevelUnlocked } from "../utils/storyLevelProgress";
import "./CreateStoryPage.css";
import "../components/BiLabel.css";

interface CreateStoryPageProps {
  onAddRecord: (record: NewAudioRecord) => void;
  initialTopicId?: string;
  initialImageIndex?: number;
  initialStartAtQuiz?: boolean;
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
  initialStartAtQuiz = false,
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
  const [startAtQuiz, setStartAtQuiz] = useState(initialStartAtQuiz);
  useEffect(() => {
    onSessionActiveChange?.(Boolean(selectedTopic));
    return () => onSessionActiveChange?.(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTopic]);

  useEffect(() => {
    // A workspace CTA can open a story while the learner is halfway down the
    // dashboard. Treat that as a new page-level task and place the story
    // header at the top before the recorder mounts.
    if (!initialTopicId || typeof window === "undefined") return;
    const resetScroll = () => window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    resetScroll();
    // The activity replaces a much shorter overview with a tall recorder.
    // Run once after layout so browser scroll anchoring cannot restore the
    // old dashboard position while the new activity settles.
    const frame = window.requestAnimationFrame(resetScroll);
    const timer = window.setTimeout(resetScroll, 40);
    return () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(timer);
    };
  }, [initialTopicId, initialImageIndex, initialStartAtQuiz]);

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

  const openTopicAtLevel = (topic: Topic, options?: TopicStartOptions) => {
    // The topic list can be long, so the click often happens near its bottom.
    // A newly opened activity is a new page-level task; start the student at
    // its header instead of preserving the catalogue's scroll position.
    if (typeof window !== "undefined") {
      window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    }
    setSelectedTopic(topic);
    setStartAtQuiz(Boolean(options?.startAtQuiz));
    setSelectedImage(topic.images[0]);
    setSelectedImageIndex(0);
  };

  const handleTopicSelect = (topic: Topic, options?: TopicStartOptions) => {
    openTopicAtLevel(topic, options);
  };

  const handleLevelSelect = (
    topic: Topic,
    level: Parameters<typeof storyToTopic>[1],
    options?: TopicStartOptions,
  ) => {
    if (!topic.sourceStory || !level) return;
    // TopicSelector disables locked tiers, but keep the policy at this
    // navigation boundary too: a stale click/event or a future caller must
    // not construct a Medium/Hard topic before its predecessor was fully
    // submitted.
    if (!isStoryLevelUnlocked(topic.sourceStory.id, level)) return;
    openTopicAtLevel(storyToTopic(topic.sourceStory, level, "approved"), options);
  };

  const handleBack = () => {
    setSelectedTopic(null);
    setStartAtQuiz(false);
    setSelectedImage("");
    setSelectedImageIndex(0);
  };

  return (
    <div className="create-story-page">
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
            startAtQuiz={startAtQuiz}
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

