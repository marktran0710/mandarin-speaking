import type { CustomStoryFrame, CustomTeacherStory, StoryDifficultyLevel } from "./types";

const BACKEND_URL =
  import.meta.env.VITE_BACKEND_URL ||
  (import.meta.env.DEV && typeof window !== "undefined" ? window.location.origin : "");

/** Resolve a relative /uploads/... URL to an absolute backend URL. */
export function resolveImageUrl(url: string): string {
  if (!url) return url;
  if (url.startsWith("/uploads/")) return `${BACKEND_URL}${url}`;
  return url;
}

export const TIER_SUFFIX: Record<StoryDifficultyLevel, ""  | "Medium" | "Hard"> = {
  easy: "",
  medium: "Medium",
  hard: "Hard",
};

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

/** Read a frame's text for the given tier, falling back to the base (Easy)
 * field when that tier hasn't been authored yet — so a partially-filled-in
 * Medium/Hard story still shows workable content instead of blanks. */
export function tierText(
  frame: CustomStoryFrame,
  base: TieredField,
  level: StoryDifficultyLevel,
): string | undefined {
  const baseValue = frame[base];
  if (level === "easy") return baseValue;
  const suffixed = frame[`${base}${TIER_SUFFIX[level]}` as keyof CustomStoryFrame] as
    | string
    | undefined;
  return suffixed && suffixed.trim() ? suffixed : baseValue;
}

/** Whether a story has any teacher-authored content for Medium/Hard beyond
 * the Easy fields — lets the student-facing tier controls hide tiers that
 * would just silently fall back to Easy text. */
export function storyHasTierContent(
  story: CustomTeacherStory,
  level: "medium" | "hard",
): boolean {
  const suffix = TIER_SUFFIX[level];
  const fields: TieredField[] = [
    "imageUrl",
    "prompt",
    "vocabulary",
    "vocabularyPinyin",
    "vocabularyPos",
    "vocabularyTranslation",
    "phrases",
    "phrasesTranslation",
    "suggestedAnswer",
    "listenAudioUrl",
    "listenScript",
  ];
  return story.frames.some((frame) =>
    fields.some((base) => {
      const value = frame[`${base}${suffix}` as keyof CustomStoryFrame] as string | undefined;
      return Boolean(value && value.trim());
    }),
  );
}

