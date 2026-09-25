import type { Topic } from "./types";

export function buildSceneReferenceCurves(
  topic: Pick<Topic, "vocabulary" | "vocabularyReferenceCurves" | "sentenceReferenceCurves">,
  sceneIndex: number,
): Record<string, number[]> | null {
  const byWord: Record<string, number[]> = { ...(topic.sentenceReferenceCurves?.[sceneIndex] || {}) };
  const words = topic.vocabulary[sceneIndex] || [];
  const curves = topic.vocabularyReferenceCurves?.[sceneIndex];
  if (curves && curves.length > 0) {
    words.forEach((word, index) => {
      const curve = curves[index];
      if (curve && curve.length > 0 && !byWord[word]) byWord[word] = curve;
    });
  }
  return Object.keys(byWord).length > 0 ? byWord : null;
}

export function vocabTooltip(pos?: string, translation?: string): string | undefined {
  if (pos && translation) return `(${pos}) ${translation}`;
  if (pos) return `(${pos})`;
  return translation;
}
