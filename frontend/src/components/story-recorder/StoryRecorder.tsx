import { createPortal } from "react-dom";
import { useEffect, useMemo, useState, type ComponentType } from "react";
import type { HelpRequest } from "../../services/database";
import StoryRecorderRuntime from "./StoryRecorderRuntime";
import SpeakingConversationFlow from "./SpeakingConversationFlow";
import SpeakingModeChooser from "./SpeakingModeChooser";
import SpeakingVocabularyPreview from "./SpeakingVocabularyPreview";
import type { NewAudioRecord } from "./StoryRecorder/types";
import type { Topic } from "./StoryRecorder/storyContent";
import { normalizeConversationTurns } from "./StoryRecorder/conversation";
import { speakingVocabularyItems } from "../../utils/speakingVocabulary";
import { BiLabel } from "../ui/BiLabel";

export interface StoryRecorderProps {
  topic: Topic;
  selectedImage: string;
  selectedImageIndex: number;
  onImageSelect: (index: number) => void;
  onImageChange: (image: string) => void;
  onAddRecord: (record: NewAudioRecord) => Promise<string | undefined> | void;
  enableSorting?: boolean;
  enableOverview?: boolean;
  startAtQuiz?: boolean;
  studentName?: string;
  studentId?: string;
  onExit?: () => void;
  helpRequests?: HelpRequest[];
  onRaiseHand?: (message: string) => void;
}

const TypedStoryRecorder = StoryRecorderRuntime as ComponentType<StoryRecorderProps>;

function StudyScriptCard({ topic, selectedImageIndex }: Pick<StoryRecorderProps, "topic" | "selectedImageIndex">) {
  const [target, setTarget] = useState<HTMLElement | null>(null);
  const script = topic.listenScripts?.[selectedImageIndex]?.trim()
    || topic.suggestedAnswers?.[selectedImageIndex]?.trim()
    || topic.prompts?.[selectedImageIndex]?.trim();

  useEffect(() => {
    if (typeof document === "undefined" || !document.body) return;
    let mounted = true;
    const findTarget = () => {
      const next = document.querySelector<HTMLElement>(
        ".practice-workspace-study .practice-scene-col",
      );
      if (mounted) setTarget((current) => (current === next ? current : next));
    };
    findTarget();
    const observer = new MutationObserver(findTarget);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => {
      mounted = false;
      observer.disconnect();
    };
  }, [selectedImageIndex, topic.id]);

  if (!target || !script) return null;
  return createPortal(
    <article className="practice-study-script" aria-label="Scene dialogue">
      <p className="practice-study-script-label">
        <BiLabel zh="本場景對話" pinyin="Běn chǎngjǐng duìhuà" en="Scene dialogue" />
      </p>
      <p className="practice-study-script-text" lang="zh-TW">{script}</p>
    </article>,
    target,
  );
}

// One-Time Vocabulary Preview plan: shown once per Story Practice session
// (a browser tab session, not forever) - a refresh must resume speaking,
// not re-show the preview, but leaving Story Practice and starting it
// again should. sessionStorage (survives refresh, clears on tab close)
// plus clearing the flag on an explicit exit gets both halves right.
function vocabularyPreviewSeenKey(storyId: string): string {
  return `storySpeakingVocabularyPreviewSeen:${storyId}`;
}

function hasSeenVocabularyPreviewThisSession(storyId: string): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.sessionStorage.getItem(vocabularyPreviewSeenKey(storyId)) === "true";
  } catch {
    return false;
  }
}

function markVocabularyPreviewSeen(storyId: string): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(vocabularyPreviewSeenKey(storyId), "true");
  } catch {
    /* sessionStorage unavailable - the preview just shows again next time */
  }
}

function clearVocabularyPreviewSeen(storyId: string): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(vocabularyPreviewSeenKey(storyId));
  } catch {
    /* nothing to clean up if storage was never reachable */
  }
}

/** One-Time Vocabulary Preview plan, Epic C: Story Practice only (never
 * Conversation Practice, which has its own listen-then-respond flow) -
 * shows the exact quiz vocabulary once, right before scenes, instead of
 * the legacy per-scene Study step repeating it every time. Epic D
 * (removing that per-scene Study step from the legacy runtime itself) is
 * intentionally out of scope - see the runtime-editing note on
 * StoryRecorderRuntime above.
 *
 * The runtime (a minified bundle this wrapper never edits into) always
 * mounts and handles overview / vocab quiz / scene navigation exactly as
 * before - this never gates in front of it (an earlier version did, and
 * incorrectly blocked reaching the quiz/overview screens for any student
 * whose speaking was already unlocked from a prior visit). Instead this
 * watches for the same ".practice-stage" DOM marker StudyScriptCard
 * already watches for, and shows the preview as a dismissible overlay
 * only once the runtime has organically reached that phase - regardless
 * of whether it got there by auto-advancing after the quiz, by the
 * student clicking "Speaking Practice" from the overview, or by resuming
 * a remembered phase. Because the overlay only appears once that DOM is
 * already rendered, it can never race or interrupt the runtime's own
 * quiz-to-practice handoff the way reactively polling localStorage did
 * (tried and reverted for exactly that reason).
 */
function StoryPracticeWithVocabularyPreview(props: StoryRecorderProps) {
  const previewItems = useMemo(() => speakingVocabularyItems(props.topic), [props.topic]);
  const [previewDismissed, setPreviewDismissed] = useState(() =>
    hasSeenVocabularyPreviewThisSession(props.topic.id),
  );
  const [practiceStageVisible, setPracticeStageVisible] = useState(false);

  useEffect(() => {
    setPreviewDismissed(hasSeenVocabularyPreviewThisSession(props.topic.id));
    setPracticeStageVisible(false);
  }, [props.topic.id]);

  useEffect(() => {
    if (typeof document === "undefined" || !document.body) return;
    let mounted = true;
    const checkPracticeStage = () => {
      const present = Boolean(document.querySelector(".practice-stage"));
      if (mounted) setPracticeStageVisible((current) => (current === present ? current : present));
    };
    checkPracticeStage();
    const observer = new MutationObserver(checkPracticeStage);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => {
      mounted = false;
      observer.disconnect();
    };
  }, [props.topic.id]);

  const handleExit = () => {
    clearVocabularyPreviewSeen(props.topic.id);
    props.onExit?.();
  };

  const showPreviewOverlay =
    Boolean(previewItems.length) && practiceStageVisible && !previewDismissed;

  return <>
    <TypedStoryRecorder {...props} onExit={props.onExit ? handleExit : undefined} />
    <StudyScriptCard topic={props.topic} selectedImageIndex={props.selectedImageIndex} />
    {showPreviewOverlay && (
      <SpeakingVocabularyPreview
        items={previewItems}
        onStart={() => {
          markVocabularyPreviewSeen(props.topic.id);
          setPreviewDismissed(true);
        }}
      />
    )}
  </>;
}

type SpeakingMode = "choose" | "story" | "conversation";

function StoryRecorderWithStudyScript(props: StoryRecorderProps) {
  const conversationTurns = useMemo(
    () => normalizeConversationTurns(props.topic.conversationTurns),
    [props.topic.conversationTurns],
  );
  // Epic 4: Conversation Practice is a second Speaking mode, chosen
  // explicitly, never a silent replacement for Story Practice. Resets to
  // the chooser on every new story so switching topics doesn't strand the
  // student in whichever mode a previous story happened to use.
  const [mode, setMode] = useState<SpeakingMode>("choose");
  useEffect(() => {
    setMode("choose");
  }, [props.topic.id]);

  if (!conversationTurns) {
    return <StoryPracticeWithVocabularyPreview key={props.topic.id} {...props} />;
  }

  if (mode === "choose") {
    return (
      <SpeakingModeChooser
        exchangeCount={conversationTurns.length / 2}
        onChooseStory={() => setMode("story")}
        onChooseConversation={() => setMode("conversation")}
      />
    );
  }

  if (mode === "conversation") {
    return (
      <SpeakingConversationFlow
        topic={props.topic}
        turns={conversationTurns}
        selectedImage={props.selectedImage}
        selectedImageIndex={props.selectedImageIndex}
        onAddRecord={props.onAddRecord}
        studentId={props.studentId}
        studentName={props.studentName}
      />
    );
  }

  return <StoryPracticeWithVocabularyPreview key={props.topic.id} {...props} />;
}

export default StoryRecorderWithStudyScript;

export {
  attemptHistoryFromAudioRecords,
  practiceSceneIndicesFor,
  sceneSubmissionFromAudioRecord,
} from "./StoryRecorderRuntime";

export {
  buildSceneReferenceCurves,
  vocabTooltip,
} from "./StoryRecorder/storyContent";

export { normalizeConversationTurns } from "./StoryRecorder/conversation";

export type {
  ConversationSpeaker,
  ConversationTurn,
} from "./StoryRecorder/conversation";

export {
  createConversationState,
  currentConversationTurn,
  isStudentRecordingStep,
  shouldAnalyzeConversationTurn,
  transitionConversation,
} from "./StoryRecorder/conversationCoordinator";

export type {
  ConversationEvent,
  ConversationState,
  ConversationStep,
  ConversationTransition,
} from "./StoryRecorder/conversationCoordinator";

export type {
  AiProviderOption,
  SpeechModel,
  Topic,
} from "./StoryRecorder/storyContent";

export type {
  ContentDiffSegment,
  DiagnosticStatus,
  NewAudioRecord,
  PauseAnalysis,
  PraatMetrics,
  ScoreProvenance,
  TranscriptionItem,
  VowelStatus,
  VowelZone,
  WordProsody,
  WordProsodySyllable,
} from "./StoryRecorder/types";
