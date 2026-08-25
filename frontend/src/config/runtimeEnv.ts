type ViteImportMeta = ImportMeta & {
  env?: Record<string, string | boolean | undefined>;
};

const viteEnv = (import.meta as ViteImportMeta).env ?? {};
const nextBackendUrl = typeof process !== "undefined" ? process.env.NEXT_PUBLIC_BACKEND_URL : "";
const viteBackendUrl = typeof viteEnv.VITE_BACKEND_URL === "string" ? viteEnv.VITE_BACKEND_URL : "";

export function getBackendUrl(): string {
  return nextBackendUrl || viteBackendUrl || (typeof window !== "undefined" ? window.location.origin : "");
}

export function getVoiceTestAsrModel(): string {
  const nextModel = typeof process !== "undefined" ? process.env.NEXT_PUBLIC_VOICE_TEST_ASR_MODEL : "";
  const viteModel = typeof viteEnv.VITE_VOICE_TEST_ASR_MODEL === "string" ? viteEnv.VITE_VOICE_TEST_ASR_MODEL : "";
  return nextModel || viteModel || "ctwhisper";
}

export function isTestRuntime(): boolean {
  return viteEnv.MODE === "test" || (typeof process !== "undefined" && (process.env.NODE_ENV === "test" || process.env.VITEST === "true"));
}

export function isDevelopmentRuntime(): boolean {
  return viteEnv.DEV === true || (typeof process !== "undefined" && process.env.NODE_ENV === "development");
}
