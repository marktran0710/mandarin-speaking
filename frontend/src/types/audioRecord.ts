/** Extracted from the deleted pages/MyStoriesPage.tsx — many teacher/admin
 * files import this type only (never the page component), so it belongs in
 * a shared location instead of a presentation file. */
export interface AudioRecord {
  id: string;
  timestamp: string;
  duration: number;
  transcription: string;
  model: string;
  topicId?: string;
  studentId?: string | null;
  imageUrl?: string;
  imageIndex?: number;
  audioUrl?: string;
  praatMetrics?: any;
}
