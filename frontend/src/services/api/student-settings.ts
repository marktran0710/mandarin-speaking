import { BACKEND_URL, fetchWithRetry } from "@shared/api/client";

export type StudentMascot = "male" | "female";
export type PartnerMascot = "fox" | "male" | "female";
export type VoiceHintMode = "auto" | "avatar";

export interface StudentSettings {
  studentMascot: StudentMascot;
  partnerMascot: PartnerMascot;
  voiceHintMode: VoiceHintMode;
}

export type StudentSettingsUpdate = Partial<StudentSettings>;

export class StudentSettingsApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "StudentSettingsApiError";
    this.status = status;
  }
}

const DEFAULT_SETTINGS: StudentSettings = {
  studentMascot: "male",
  partnerMascot: "fox",
  voiceHintMode: "auto",
};

async function parseError(response: Response, fallback: string): Promise<StudentSettingsApiError> {
  const body = await response.clone().json().catch(() => null) as { detail?: unknown } | null;
  return new StudentSettingsApiError(
    typeof body?.detail === "string" ? body.detail : fallback,
    response.status,
  );
}

function normalizeSettings(value: unknown): StudentSettings {
  const row = value as Partial<StudentSettings> | null;
  return {
    studentMascot: row?.studentMascot === "female" ? "female" : DEFAULT_SETTINGS.studentMascot,
    partnerMascot: row?.partnerMascot === "male" || row?.partnerMascot === "female"
      ? row.partnerMascot
      : DEFAULT_SETTINGS.partnerMascot,
    voiceHintMode: row?.voiceHintMode === "avatar" ? "avatar" : DEFAULT_SETTINGS.voiceHintMode,
  };
}

export async function getStudentSettings(): Promise<StudentSettings> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/students/me/settings`);
  if (!response.ok) throw await parseError(response, "Could not load student settings.");
  return normalizeSettings(await response.json());
}

export async function updateStudentSettings(update: StudentSettingsUpdate): Promise<StudentSettings> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/students/me/settings`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(update),
  });
  if (!response.ok) throw await parseError(response, "Could not save student settings.");
  return normalizeSettings(await response.json());
}

export async function changeStudentPassword(currentPassword: string, newPassword: string): Promise<void> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/students/me/password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ currentPassword, newPassword }),
  });
  if (!response.ok) throw await parseError(response, "Could not change password.");
}

