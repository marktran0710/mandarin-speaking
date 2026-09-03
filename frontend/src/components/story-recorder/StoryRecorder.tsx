import { createPortal } from "react-dom";
import { useEffect, useState, type ComponentType } from "react";
import type { HelpRequest } from "../../services/database";
import StoryRecorderRuntime from "./StoryRecorderRuntime";
import type { NewAudioRecord } from "./StoryRecorder/types";
import type { Topic } from "./StoryRecorder/storyContent";
import { BiLabel } from "../BiLabel";

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

function StoryRecorderWithStudyScript(props: StoryRecorderProps) {
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
