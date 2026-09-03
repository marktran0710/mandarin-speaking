import type { WordProsody } from "./types";

export function normalizeWavFileName(fileName: string): string {
  return fileName.toLowerCase().endsWith(".wav") ? fileName : `${fileName}.wav`;
}

export function ensureWavBlob(blob: Blob): Blob {
  if (blob.type === "audio/wav" || blob.type === "audio/x-wav") return blob;
  return new Blob([blob], { type: "audio/wav" });
}

export function readErrorResponse(response: Response): Promise<{ detail?: string }> {
  return response.json().catch(() => ({ detail: `${response.status} ${response.statusText}` }));
}

export function formatBackendError(error: unknown, backendUrl: string): string {
  const message = error instanceof Error ? error.message : String(error);
  const networkFailures = ["Failed to fetch", "NetworkError", "Load failed"];
  if (networkFailures.some((failure) => message.includes(failure))) {
    return `無法連線到語音分析伺服器 (${backendUrl})，請先啟動 FastAPI 後端（8000 埠），再試一次。 Cannot reach the speech analysis backend at ${backendUrl}. Start the FastAPI backend on port 8000, then try again.`;
  }
  return message || "語音分析發生錯誤。 Voice analysis error occurred.";
}

export function normalizeWordProsody(words: WordProsody[] = []) {
  return words.map((word, index) => ({
    token: word.token, index: word.index ?? index, start_time: word.start_time ?? index,
    end_time: word.end_time ?? index + 1, pitch_contour: word.pitch_contour ?? [],
    reference_contour: word.reference_contour ?? [], mean_pitch: word.mean_pitch,
    pitch_range: word.pitch_range, start_pitch: word.start_pitch ?? word.mean_pitch,
    end_pitch: word.end_pitch ?? word.mean_pitch, contour_shape: word.contour_shape,
    feedback: word.feedback,
  }));
}
