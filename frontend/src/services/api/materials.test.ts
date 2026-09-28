import { beforeEach, describe, expect, it, vi } from "vitest";

const { fetchWithRetry } = vi.hoisted(() => ({ fetchWithRetry: vi.fn() }));

vi.mock("@shared/api/client", () => ({
  BACKEND_URL: "http://backend.test",
  fetchWithRetry,
}));

import { confirmMaterialsImport, MATERIALS_IMPORT_TIMEOUT_MS, previewMaterialsImport } from "./materials";

describe("materials import API", () => {
  beforeEach(() => fetchWithRetry.mockReset());

  it("uses an extended timeout for preview and confirmation", async () => {
    const responseBody = JSON.stringify({
      kind: "scripts",
      rows: 1,
      changes: [],
      issues: [],
      valid: true,
      updated: [],
      stories: [],
    });
    fetchWithRetry
      .mockResolvedValueOnce(new Response(responseBody, { status: 200 }))
      .mockResolvedValueOnce(new Response(responseBody, { status: 200 }));
    const file = new File(["lesson,story,scene,character,script\n5,1,1,中明,你好"], "lessons-5-8.csv", { type: "text/csv" });

    await previewMaterialsImport("scripts", [file]);
    await confirmMaterialsImport("scripts", [file]);

    expect(fetchWithRetry).toHaveBeenNthCalledWith(
      1,
      "http://backend.test/api/admin/materials/scripts/preview",
      expect.objectContaining({ method: "POST", body: expect.any(FormData) }),
      1,
      MATERIALS_IMPORT_TIMEOUT_MS,
    );
    expect(fetchWithRetry).toHaveBeenNthCalledWith(
      2,
      "http://backend.test/api/admin/materials/scripts/confirm",
      expect.objectContaining({ method: "POST", body: expect.any(FormData) }),
      1,
      MATERIALS_IMPORT_TIMEOUT_MS,
    );
  });
});
