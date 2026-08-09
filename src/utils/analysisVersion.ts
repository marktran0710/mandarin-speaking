export type AnalysisVersion = "stable_v1" | "phoneme_tone_v2";

export const STABLE_ANALYSIS_VERSION: AnalysisVersion = "stable_v1";
export const EXPERIMENTAL_ANALYSIS_VERSION: AnalysisVersion = "phoneme_tone_v2";

const KEY_PREFIX = "analysisVersion:";

export function isAnalysisVersion(value: unknown): value is AnalysisVersion {
  return value === STABLE_ANALYSIS_VERSION || value === EXPERIMENTAL_ANALYSIS_VERSION;
}

export function analysisVersionStorageKey(studentScope: string): string {
  return `${KEY_PREFIX}${studentScope || "guest"}`;
}

export function getAnalysisVersion(studentScope = "guest"): AnalysisVersion {
  try {
    const value = localStorage.getItem(analysisVersionStorageKey(studentScope));
    return isAnalysisVersion(value) ? value : STABLE_ANALYSIS_VERSION;
  } catch {
    return STABLE_ANALYSIS_VERSION;
  }
}

export function saveAnalysisVersion(version: AnalysisVersion, studentScope = "guest") {
  try {
    localStorage.setItem(analysisVersionStorageKey(studentScope), version);
  } catch {
    // Storage is optional; Stable V1 remains the safe in-memory fallback.
  }
}
