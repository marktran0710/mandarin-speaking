import { buildSceneReferenceCurves, vocabTooltip } from "@entities/topic";
export type { SpeechModel } from "@entities/speech";

export interface AiProviderOption {
  id: string;
  label: string;
  available: boolean;
}

export type { Topic } from "@entities/topic";
export { buildSceneReferenceCurves, vocabTooltip };
