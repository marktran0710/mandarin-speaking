import { getBackendUrl } from "../../config/runtimeEnv";

export interface GeneratedFrame {
  index: number;
  title: string;
  student_prompt: string;
  vocabulary: string[];
  image_prompt: string;
  image_url: string;
}

export interface GeneratedStory {
  provider: string;
  title: string;
  learning_goal: string;
  frames: GeneratedFrame[];
}

export async function generateStoryImages(input: {
  situation: string;
  level: string;
  style: string;
  language_focus: string;
}): Promise<GeneratedStory> {
  const response = await fetch(`${getBackendUrl()}/api/generate-story-images`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const data = await response.json() as { detail?: unknown };
      if (typeof data.detail === "string" && data.detail.trim()) detail = data.detail;
    } catch {
      // Keep the HTTP fallback when the backend returns a non-JSON error.
    }
    throw new Error(detail);
  }
  return response.json() as Promise<GeneratedStory>;
}
