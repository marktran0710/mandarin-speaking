import type { CustomStoryFrame, CustomTeacherStory } from "./teacherStories";

const BACKEND_URL =
  import.meta.env.VITE_BACKEND_URL ||
  (import.meta.env.DEV ? "http://127.0.0.1:8000" : "");

const EXPORT_FORMAT = "enjoyable-mandarin-story";
const EXPORT_VERSION = 1;

interface StoryExportFile {
  format: typeof EXPORT_FORMAT;
  version: typeof EXPORT_VERSION;
  exportedAt: string;
  story: CustomTeacherStory;
}

/**
 * Inlines a /uploads/... or external URL as a base64 data URL, so the
 * exported file has no dependency on the original backend. Routed through
 * our own backend's /api/inline-media rather than fetched directly from the
 * browser: story images generated via DALL-E/Pollinations.ai keep their
 * original third-party URL, and those hosts don't grant CORS permission for
 * arbitrary origins, so a direct browser fetch() is blocked. A server-to-
 * server request has no such restriction.
 */
async function inlineAsDataUrl(url: string): Promise<string> {
  if (!url || url.startsWith("data:")) return url;

  const response = await fetch(
    `${BACKEND_URL}/api/inline-media?url=${encodeURIComponent(url)}`,
  );
  if (!response.ok) {
    throw new Error(`Could not download "${url}" while preparing the export.`);
  }
  const { dataUrl } = await response.json();
  return dataUrl;
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
