import type { CustomStoryFrame, CustomTeacherStory } from "./teacherStories";
import { resolveImageUrl } from "./teacherStories";

const EXPORT_FORMAT = "enjoyable-mandarin-story";
const EXPORT_VERSION = 1;

interface StoryExportFile {
  format: typeof EXPORT_FORMAT;
  version: typeof EXPORT_VERSION;
  exportedAt: string;
  story: CustomTeacherStory;
}

/** Fetches a /uploads/... or external URL and inlines it as a base64 data URL,
 * so the exported file has no dependency on the original backend. */
async function inlineAsDataUrl(url: string): Promise<string> {
  if (!url || url.startsWith("data:")) return url;

  const response = await fetch(resolveImageUrl(url));
  if (!response.ok) {
    throw new Error(`Could not download "${url}" while preparing the export.`);
  }
  const blob = await response.blob();

  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error(`Could not read "${url}" while preparing the export.`));
    reader.onload = () => resolve(typeof reader.result === "string" ? reader.result : "");
    reader.readAsDataURL(blob);
  });
}

async function inlineFrameMedia(frame: CustomStoryFrame): Promise<CustomStoryFrame> {
  const imageUrl = await inlineAsDataUrl(frame.imageUrl);
  const listenAudioUrl = frame.listenAudioUrl
    ? await inlineAsDataUrl(frame.listenAudioUrl)
    : frame.listenAudioUrl;

  return { ...frame, imageUrl, ...(listenAudioUrl ? { listenAudioUrl } : {}) };
}

function slugifyTitle(title: string): string {
  const slug = title
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug || "story";
}

/**
 * Packages a story into a self-contained .json file (images/audio inlined as
 * base64) and triggers a browser download, so it can be handed to another
 * device with no shared backend and imported there.
 */
export async function exportStoryFile(story: CustomTeacherStory): Promise<void> {
  const frames = await Promise.all(story.frames.map(inlineFrameMedia));
  const payload: StoryExportFile = {
    format: EXPORT_FORMAT,
    version: EXPORT_VERSION,
    exportedAt: new Date().toISOString(),
    story: { ...story, frames },
  };

  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${slugifyTitle(story.title)}.mandarin-story.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function isCustomStoryFrame(value: unknown): value is CustomStoryFrame {
  if (!value || typeof value !== "object") return false;
  const frame = value as Record<string, unknown>;
  return typeof frame.imageUrl === "string" && typeof frame.prompt === "string";
}

/**
 * Parses and validates a file produced by exportStoryFile, assigning it a
 * fresh id and unpublished state so it lands as a new draft that the
 * receiving teacher can review before publishing.
 */
export async function readStoryImportFile(file: File): Promise<CustomTeacherStory> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(await file.text());
  } catch {
    throw new Error("That file is not valid JSON.");
  }

  const envelope = parsed as Partial<StoryExportFile> | null;
  const story = (envelope?.story ?? parsed) as Partial<CustomTeacherStory> | null;

  if (
    !story ||
    typeof story !== "object" ||
    typeof story.title !== "string" ||
    !Array.isArray(story.frames) ||
    story.frames.length === 0 ||
    !story.frames.every(isCustomStoryFrame)
  ) {
    throw new Error("This file doesn't look like a story export.");
  }

  return {
    ...(story as CustomTeacherStory),
    id: `custom-story-${Date.now()}`,
    published: false,
  };
}
