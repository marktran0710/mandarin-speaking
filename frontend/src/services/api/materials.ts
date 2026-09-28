import { BACKEND_URL, fetchWithRetry } from "@shared/api/client";

export type MaterialsImportKind = "images" | "scripts";

export interface MaterialsImportChange {
  filename?: string;
  storyKey?: string;
  storyId: string;
  storyTitle: string;
  lesson?: number;
  story?: number;
  scene?: number;
  scenes?: number;
  before: string;
  after: string;
  bytes?: number;
}

export interface MaterialsImportPreview {
  kind: MaterialsImportKind;
  files?: number;
  rows?: number;
  changes: MaterialsImportChange[];
  issues: string[];
  valid: boolean;
}

export interface MaterialsImportResult {
  kind: MaterialsImportKind;
  files?: number;
  updated: Array<Record<string, unknown>>;
  stories: string[];
  alignmentRefreshed?: number;
  alignmentCleared?: number;
}

async function postMaterials<T>(kind: MaterialsImportKind, path: "preview" | "confirm", files: File[]): Promise<T> {
  const body = new FormData();
  files.forEach((file) => body.append("file", file, file.name));
  const response = await fetchWithRetry(`${BACKEND_URL}/api/admin/materials/${kind}/${path}`, { method: "POST", body }, 1);
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
    throw new Error(typeof payload?.detail === "string" ? payload.detail : "Could not process the materials import.");
  }
  return response.json() as Promise<T>;
}

export function previewMaterialsImport(kind: MaterialsImportKind, files: File[]): Promise<MaterialsImportPreview> {
  return postMaterials<MaterialsImportPreview>(kind, "preview", files);
}

export function confirmMaterialsImport(kind: MaterialsImportKind, files: File[]): Promise<MaterialsImportResult> {
  return postMaterials<MaterialsImportResult>(kind, "confirm", files);
}

export async function downloadMaterialsTemplate(kind: MaterialsImportKind): Promise<Blob> {
  const response = await fetchWithRetry(`${BACKEND_URL}/api/admin/materials/${kind}/template`);
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
    throw new Error(typeof payload?.detail === "string" ? payload.detail : "Could not download the materials template.");
  }
  return response.blob();
}
