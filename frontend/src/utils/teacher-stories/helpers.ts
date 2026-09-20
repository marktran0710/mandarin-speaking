import type { CustomStoryFrame, StoryDifficultyLevel } from "./types";
import { getBackendUrl } from "../../config/runtimeEnv";

const BACKEND_URL = getBackendUrl();

/** Resolve a relative /uploads/... URL to an absolute backend URL. */
export function resolveImageUrl(url: string): string {
  if (!url) return url;
  if (url.startsWith("/uploads/")) return `${BACKEND_URL}${url}`;
  return url;
}

// Stories run one text level; the base fields carry no suffix.
export const TIER_SUFFIX: Record<StoryDifficultyLevel, ""> = { easy: "" };

export function splitCsvField(value?: string): string[] {
  return (value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function parseJsonArray(value?: string): unknown[] | null {
  if (!value || !value.trim()) return null;
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

type TieredField =
  | "imageUrl"
  | "prompt"
  | "vocabulary"
  | "vocabularyPinyin"
  | "vocabularyPos"
  | "vocabularyTranslation"
  | "phrases"
  | "phrasesTranslation"
  | "suggestedAnswer"
  | "listenAudioUrl"
  | "listenScript";

/** Read a frame's text for the story's single level. Kept as a helper (rather
 * than inlining `frame[base]`) so the many call sites stay unchanged now that
 * the extra story-text levels are gone; the `level` argument is accepted and
 * ignored for the same reason. */
export function tierText(
  frame: CustomStoryFrame,
  base: TieredField,
  _level: StoryDifficultyLevel = "easy",
): string | undefined {
  return frame[base];
}
