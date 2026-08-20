// The browser build includes deterministic study-harness tests, but this
// workspace intentionally does not ship the full Node type package. Keep the
// small filesystem surface used by those tests typed without changing runtime
// code or the Stable/V2 application paths.
declare module "node:fs" {
  export function existsSync(path: string): boolean;
  export function mkdirSync(path: string, options?: unknown): void;
  export function writeFileSync(path: string, data: unknown, options?: unknown): void;
}

declare module "node:path" {
  export function dirname(path: string): string;
  export function resolve(...paths: string[]): string;
}

declare const __dirname: string;
