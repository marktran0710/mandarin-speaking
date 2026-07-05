const BACKEND_URL =
  import.meta.env.VITE_BACKEND_URL ||
  (import.meta.env.DEV ? "http://127.0.0.1:8000" : "");

const REQUEST_TIMEOUT_MS = 15_000;

async function fetchWithRetry(
  input: RequestInfo | URL,
  init?: RequestInit,
  maxAttempts = 3,
): Promise<Response> {
  let lastError: unknown;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    try {
      const response = await fetch(input, { ...init, signal: controller.signal });
      clearTimeout(timer);
      return response;
    } catch (err) {
      clearTimeout(timer);
      lastError = err;
      const isAbort = err instanceof DOMException && err.name === "AbortError";
      // Don't retry mutations to avoid double-writes
      const method = (init?.method ?? "GET").toUpperCase();
      if (isAbort || method !== "GET" || attempt === maxAttempts) break;
      await new Promise((r) => setTimeout(r, 300 * 2 ** (attempt - 1)));
    }
  }
  throw lastError;
}

export interface StoredAudioRecord {
  id: string;
  timestamp: string;
  duration: number;
  transcription: string;
  model: string;
  topicId?: string;
  imageUrl?: string;
  imageIndex?: number;
  audioUrl?: string;
  praatMetrics?: any;
}

export interface CustomStoryFrame {
  imageUrl: string;
  prompt: string;
  vocabulary: string;
  vocabularyGroups?: Array<{ name: string; words: string[] }>;
  grammarPattern?: string;
  grammarExample?: string;
  vocabularyPinyin?: string;
  suggestedAnswer?: string;
  listenAudioUrl?: string;
  listenScript?: string;
}

export interface StoredCustomStory {
  id: string;
  title: string;
  learningGoal: string;
  level: string;
  frames: CustomStoryFrame[];
  published?: boolean;
  linear?: boolean;
  firstFrameIsExample?: boolean;
  lessonNumber?: number | null;
  narrativeMode?: NarrativeMode;
}

export type NarrativeMode = "story" | "describe" | "listen_retell";

export interface SceneSubmission {
  sceneIndex: number;
  imageUrl: string;
  transcription: string;
  vocabUsed: string[];
  vocabMissing: string[];
  vocabScore: number;
  toneAccuracy: number;
  pronScore: number;
  fluencyScore?: number;
  audioUrl?: string;
}

export interface StoryFeedbackDimension {
  score: number;
  feedback: string;
  judged?: boolean; // false = offline/local placeholder, not a real judgment
}

export interface StoryFeedback {
  provider: string;
  fluency_coherence: StoryFeedbackDimension;
  lexical_resource: StoryFeedbackDimension;
  grammatical_range_accuracy: StoryFeedbackDimension;
  pronunciation: StoryFeedbackDimension;
}

export interface StorySubmission {
  id: string;
  storyId: string;
  storyTitle: string;
  studentName: string;
  submittedAt: string;
  scenes: SceneSubmission[];
  concatenatedAudioUrl?: string | null;
  storyFeedback?: StoryFeedback | null;
}

export interface HelpRequest {
  id: string;
  studentName: string;
  message: string;
  status: "open" | "resolved";
  createdAt: string;
  resolvedAt?: string | null;
}

export function canUseDatabase(): boolean {
  return Boolean(BACKEND_URL) && import.meta.env.MODE !== "test";
}

export async function listAudioRecords(): Promise<StoredAudioRecord[]> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/audio-records`);
  if (!response.ok) {
    throw new Error("Could not load audio records from the database.");
  }

  const records = await response.json();
  return Array.isArray(records) ? records : [];
}

export async function createAudioRecord(
  record: StoredAudioRecord,
  audioBlob?: Blob,
) {
  const response = audioBlob
    ? await uploadAudioRecord(record, audioBlob)
    : await fetchWithRetry(`${BACKEND_URL}/api/audio-records`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(record),
      });

  if (!response.ok) {
    throw new Error("Could not save audio record to the database.");
  }

  return response.json() as Promise<StoredAudioRecord>;
}

async function uploadAudioRecord(record: StoredAudioRecord, audioBlob: Blob) {
  const formData = new FormData();
  formData.append("record", JSON.stringify(record));
  formData.append("file", audioBlob, `${record.id}.wav`);

  return fetchWithRetry(`${BACKEND_URL}/api/audio-records/upload`, {
    method: "POST",
    body: formData,
  });
}

export async function deleteAudioRecordFromDatabase(id: string) {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/audio-records/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    throw new Error("Could not delete audio record from the database.");
  }
}

export async function listCustomStories(): Promise<StoredCustomStory[]> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/custom-stories`);
  if (!response.ok) {
    throw new Error("Could not load custom stories from the database.");
  }

  const stories = await response.json();
  return Array.isArray(stories) ? stories : [];
}

export async function createCustomStory(
  story: StoredCustomStory,
): Promise<StoredCustomStory> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/custom-stories`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(story),
  });

  if (!response.ok) {
    throw new Error("Could not save custom story to the database.");
  }

  // The backend writes any uploaded data-URL images to disk and returns the
  // frames with lightweight /uploads/images/... URLs in their place.
  return response.json() as Promise<StoredCustomStory>;
}

export async function deleteCustomStoryFromDatabase(id: string) {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/custom-stories/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    throw new Error("Could not delete custom story from the database.");
  }
}

export async function listHelpRequests(): Promise<HelpRequest[]> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/help-requests`);
  if (!response.ok) {
    throw new Error("Could not load help requests from the database.");
  }

  const requests = await response.json();
  return Array.isArray(requests) ? requests : [];
}

export async function createHelpRequest(request: HelpRequest) {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/help-requests`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error("Could not send the help request.");
  }

  return response.json() as Promise<HelpRequest>;
}

export async function listStorySubmissions(storyId?: string): Promise<StorySubmission[]> {
  const url = storyId
    ? `${BACKEND_URL}/api/story-submissions?story_id=${encodeURIComponent(storyId)}`
    : `${BACKEND_URL}/api/story-submissions`;
  const response = await fetchWithRetry(url);
  if (!response.ok) throw new Error("Could not load story submissions.");
  const data = await response.json();
  return Array.isArray(data) ? data : [];
}

export async function createStorySubmission(submission: StorySubmission): Promise<StorySubmission> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/story-submissions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(submission),
  });
  if (!response.ok) throw new Error("Could not submit story.");
  return response.json() as Promise<StorySubmission>;
}

export async function resolveHelpRequest(id: string) {
  const response = await fetchWithRetry(
    `${BACKEND_URL}/api/help-requests/${encodeURIComponent(id)}/resolve`,
    { method: "POST" },
  );

  if (!response.ok) {
    throw new Error("Could not resolve the help request.");
  }

  return response.json() as Promise<HelpRequest>;
}
