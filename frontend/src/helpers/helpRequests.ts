import type { HelpRequest } from "../shared/api/learningApi";

const HELP_REQUESTS_KEY = "helpRequests";

export function loadLocalHelpRequests(): HelpRequest[] {
  try {
    const requests = JSON.parse(localStorage.getItem(HELP_REQUESTS_KEY) || "[]");
    return Array.isArray(requests) ? requests : [];
  } catch {
    return [];
  }
}

export function saveHelpRequestsLocally(requests: HelpRequest[]): HelpRequest[] {
  localStorage.setItem(HELP_REQUESTS_KEY, JSON.stringify(requests));
  return requests;
}

export function upsertHelpRequest(
  requests: HelpRequest[],
  nextRequest: HelpRequest,
): HelpRequest[] {
  const existingIndex = requests.findIndex((request) => request.id === nextRequest.id);
  if (existingIndex === -1) return [nextRequest, ...requests];
  return requests.map((request, index) => (index === existingIndex ? nextRequest : request));
}
