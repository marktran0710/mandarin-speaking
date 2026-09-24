import { BACKEND_URL, fetchWithRetry } from "./client";

export interface ContentDoctorFinding {
  code: string;
  severity: "error" | "warning" | string;
  storyId: string | null;
  location: string;
  detail: unknown;
  ownerType?: string;
  ownerId?: string;
}

export interface ContentDoctorLesson {
  storyId: string;
  title: string;
  lessonNumber: number | null;
  lessonSubOrder: number | null;
  published: boolean;
  sources: {
    canonicalVocabulary: string;
    speakingVocabulary: string[];
    conversation: string;
  };
  counts: {
    frames: number;
    canonicalWords: number;
    quizQuestions: number;
    speakingWords: number;
    conversationTurns: number;
    findings: number;
  };
  findings: ContentDoctorFinding[];
}

export interface ContentDoctorMediaReference {
  url: string;
  domain: string;
  ownerType: string;
  ownerId: string;
  role: string;
  kind: string;
  location: string;
  status: string;
  bytes?: number;
  mimeType?: string | null;
}

export interface ContentDoctorReport {
  generatedAt: string;
  readOnly: true;
  ownership: Record<string, string>;
  summary: {
    stories: number;
    publishedStories: number;
    canonicalWords: number;
    quizQuestions: number;
    mediaReferences: number;
    mediaByDomain: Record<string, number>;
    mediaByStatus: Record<string, number>;
    orphanFiles: number;
    findings: number;
    findingsBySeverity: Record<string, number>;
    findingsByCode: Record<string, number>;
  };
  lessons: ContentDoctorLesson[];
  media: {
    references: ContentDoctorMediaReference[];
    orphanFiles: Array<{ url: string; kind: string; bytes: number; mimeType: string | null }>;
  };
  findings: ContentDoctorFinding[];
}

export async function getContentInventory(): Promise<ContentDoctorReport> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/admin/content-inventory`);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "Could not load the content inventory report.");
  }
  return response.json() as Promise<ContentDoctorReport>;
}
