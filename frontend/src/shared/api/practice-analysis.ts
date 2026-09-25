import { getBackendUrl } from "../../utils/storyRecorderFeedback";

export async function postPracticeAnalysisStream(
  formData: FormData,
  signal: AbortSignal,
): Promise<Response> {
  return fetch(`${getBackendUrl()}/api/analyze/stream`, {
    method: "POST",
    body: formData,
    signal,
  });
}

export interface AiProviderStatus {
  id: string;
  available?: boolean;
}

export async function loadAiProviders(
  signal: AbortSignal,
): Promise<{ providers?: AiProviderStatus[] } | null> {
  const response = await fetch(`${getBackendUrl()}/api/ai-providers`, { signal });
  if (!response.ok) return null;
  return response.json() as Promise<{ providers?: AiProviderStatus[] }>;
}
