import { createPortal } from "react-dom";
import { useEffect, useMemo, useState, type ComponentType } from "react";
import type { HelpRequest } from "../../services/database";
import StoryRecorderRuntime from "./StoryRecorderRuntime";
import SpeakingConversationFlow from "./SpeakingConversationFlow";
import SpeakingModeChooser from "./SpeakingModeChooser";
import type { NewAudioRecord } from "./StoryRecorder/types";
import type { Topic } from "./StoryRecorder/storyContent";
import { normalizeConversationTurns } from "./StoryRecorder/conversation";
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
    return <>
      <TypedStoryRecorder {...props} />
      <StudyScriptCard topic={props.topic} selectedImageIndex={props.selectedImageIndex} />
    </>;
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
      />
    );
  }

  return <>
    <TypedStoryRecorder {...props} />
    <StudyScriptCard topic={props.topic} selectedImageIndex={props.selectedImageIndex} />
  </>;
}

export default StoryRecorderWithStudyScript;

export {
  attemptHistoryFromAudioRecords,
  practiceSceneIndicesFor,
  sceneSubmissionFromAudioRecord,
} from "./StoryRecorderRuntime";

export {
  buildClozePatchUpdates,
  buildDistractorPatchUpdates,
  buildSceneReferenceCurves,
  buildSynonymPatchUpdates,
  planClozeGrowth,
  planDistractorGrowth,
  planSynonymGrowth,
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
  ClozeGrowthCandidate,
  DistractorGrowthCandidate,
  SpeechModel,
  SynonymGrowthCandidate,
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
