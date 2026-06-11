const BACKEND_URL =
  import.meta.env.VITE_BACKEND_URL ||
  (import.meta.env.DEV ? "http://127.0.0.1:8000" : window.location.origin);

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
  conceptMap?: {
    characters?: string;
    place?: string;
    actions?: string;
    vocabulary?: string;
    connectors?: string;
    fullStory?: string;
  };
}

export interface StoredCustomStory {
  id: string;
  title: string;
  learningGoal: string;
  level: string;
  frames: CustomStoryFrame[];
  published?: boolean;
}

export function canUseDatabase(): boolean {
  return Boolean(BACKEND_URL) && import.meta.env.MODE !== "test";
}

export async function listAudioRecords(): Promise<StoredAudioRecord[]> {
  const response = await fetch(`${BACKEND_URL}/api/audio-records`);
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
    : await fetch(`${BACKEND_URL}/api/audio-records`, {
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

  return fetch(`${BACKEND_URL}/api/audio-records/upload`, {
    method: "POST",
    body: formData,
  });
}

export async function deleteAudioRecordFromDatabase(id: string) {
  const response = await fetch(`${BACKEND_URL}/api/audio-records/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    throw new Error("Could not delete audio record from the database.");
  }
}

export async function listCustomStories(): Promise<StoredCustomStory[]> {
  const response = await fetch(`${BACKEND_URL}/api/custom-stories`);
  if (!response.ok) {
    throw new Error("Could not load custom stories from the database.");
  }

  const stories = await response.json();
  return Array.isArray(stories) ? stories : [];
}

export async function createCustomStory(story: StoredCustomStory) {
  const response = await fetch(`${BACKEND_URL}/api/custom-stories`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(story),
  });

  if (!response.ok) {
    throw new Error("Could not save custom story to the database.");
  }
}

export async function deleteCustomStoryFromDatabase(id: string) {
  const response = await fetch(`${BACKEND_URL}/api/custom-stories/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    throw new Error("Could not delete custom story from the database.");
  }
}
