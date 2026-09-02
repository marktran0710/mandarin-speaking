import { useCallback, useEffect, useRef, useState } from "react";
import TopicSelector, { type TopicStartOptions } from "../components/TopicSelector";
import StoryRecorder, { type NewAudioRecord } from "../components/story-recorder/StoryRecorder";
import { HelpRequest } from "../services/database";
import { loadPublishedTeacherTopics, storyToTopic } from "../utils/teacherStories";
import type { Topic } from "../components/TopicSelector";
import { getStudentId, getStudentName, saveLastScenePhase } from "../utils/studentSession";
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
  /** Requests a reset of the enclosing workspace panel at a story boundary. */
  onPanelScrollBoundary?: () => void;
  /** Average tone accuracy, forwarded to the browse dashboard's stat card. */
  averageToneAccuracy?: number | null;
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
  onPanelScrollBoundary,
  averageToneAccuracy,
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
  const storyHistoryEntry = useRef(false);

  const resetToTopicList = useCallback(() => {
    onPanelScrollBoundary?.();
    setSelectedTopic(null);
    setStartAtQuiz(false);
    setSelectedImage("");
    setSelectedImageIndex(0);
  }, [onPanelScrollBoundary]);

  // Story selection is an in-page state change rather than a URL route, so
  // create one history entry for it. This makes the session header's Back
  // control behave like a real page back, including the browser Back button,
  // without sending the learner to an unrelated external history entry.
  useEffect(() => {
    const handlePopState = () => {
      if (!storyHistoryEntry.current) return;
      storyHistoryEntry.current = false;
      resetToTopicList();
    };

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [resetToTopicList]);
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

  const openTopicAtLevel = (topic: Topic, options?: TopicStartOptions) => {
    // The topic list can be long, so the click often happens near its bottom.
    // A newly opened activity is a new page-level task; start the student at
    // its header instead of preserving the catalogue's scroll position.
    onPanelScrollBoundary?.();
    // Choosing a story from the catalogue starts a new activity decision.
    // Clear any remembered in-story phase so an earlier Speaking/Quiz session
    // cannot hide the Vocabulary Quiz vs Speaking Practice chooser.
    if (!options?.startAtQuiz) saveLastScenePhase(topic.id, "overview");
    if (typeof window !== "undefined" && !storyHistoryEntry.current) {
      window.history.pushState(
        {
          ...(window.history.state ?? {}),
          mandarinPractice: { topicId: topic.id },
        },
        "",
        window.location.href,
      );
      storyHistoryEntry.current = true;
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
    if (storyHistoryEntry.current && typeof window !== "undefined") {
      window.history.back();
      return;
    }
    resetToTopicList();
  };

  return (
    <div className="create-story-page">
      {!selectedTopic ? (
        <TopicSelector
          onTopicSelect={handleTopicSelect}
          onLevelSelect={handleLevelSelect}
          averageToneAccuracy={averageToneAccuracy}
        />
      ) : (
        <div className="csp-recorder-body">
          {/* The catalogue chooses the story; this overview chooses the
            activity the student wants to do next. */}
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

