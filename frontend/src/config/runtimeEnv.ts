type ViteImportMeta = ImportMeta & {
  env?: Record<string, string | boolean | undefined>;
};

const viteEnv = (import.meta as ViteImportMeta).env ?? {};
const viteBackendUrl = typeof viteEnv.VITE_BACKEND_URL === "string" ? viteEnv.VITE_BACKEND_URL : "";

export function getBackendUrl(): string {
  return viteBackendUrl || (typeof window !== "undefined" ? window.location.origin : "");
}

export function isTestRuntime(): boolean {
  return viteEnv.MODE === "test";
}

export function isDevelopmentRuntime(): boolean {
  return viteEnv.DEV === true;
}
