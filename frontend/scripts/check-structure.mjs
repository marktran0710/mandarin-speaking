import { readdir, readFile } from "node:fs/promises";
import path from "node:path";

const src = path.resolve("src");
const LEGACY_SHIM_BASELINE = 0;
const allowedTopLevel = new Set([
  "app", "components", "config", "data", "entities", "features", "helpers",
  "hooks", "i18n", "integration", "services", "shared",
  "styles", "test", "types", "utils",
]);
const errors = [];
const warnings = [];
let shimCount = 0;

function relative(file) {
  return path.relative(src, file).replaceAll(path.sep, "/");
}

async function visit(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const fullPath = path.join(directory, entry.name);
    const rel = relative(fullPath);
    if (entry.isDirectory()) {
      if (directory === src && !allowedTopLevel.has(entry.name)) {
        errors.push(`${rel}: src/ contains an unapproved top-level directory`);
      }
      if (entry.name !== "src" && !/^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/.test(entry.name)) {
        errors.push(`${rel}: directory names must be kebab-case`);
      }
      await visit(fullPath);
      continue;
    }
    if (!/\.(?:ts|tsx)$/.test(entry.name)) continue;
    const text = await readFile(fullPath, "utf8");
    shimCount += (text.match(/LEGACY-SHIM/g) ?? []).length;
    if (/^(?:utils|helpers|misc|common)\.(?:tsx?|jsx?)$/.test(entry.name)) {
      errors.push(`${rel}: generic utility filenames are not allowed`);
    }
    if (/^[A-Z]\w*\.[A-Za-z]\w*\.tsx?$/.test(entry.name) && !entry.name.includes(".test.") && !entry.name.endsWith(".d.ts")) {
      errors.push(`${rel}: dotted pseudo-folders are not allowed`);
    }
    if (/\bfetch\s*\(/.test(text) && entry.name !== "api.ts" && !rel.startsWith("shared/api/")) {
      errors.push(`${rel}: fetch() belongs in an api.ts module or shared/api/`);
    }
    const lines = text.split(/\r?\n/).length;
    const limit = entry.name.endsWith(".tsx") ? 250 : 300;
    if (lines >= 500) errors.push(`${rel}: ${lines} lines (500-line limit)`);
    else if (lines >= limit) warnings.push(`${rel}: ${lines} lines (review at ${limit})`);
  }
}

await visit(src);
if (shimCount > LEGACY_SHIM_BASELINE) errors.push(`LEGACY-SHIM count is ${shimCount}; baseline allows ${LEGACY_SHIM_BASELINE}`);
for (const warning of warnings) console.warn(`warning: ${warning}`);
for (const error of errors) console.error(`error: ${error}`);
if (errors.length) process.exit(1);
console.log(`structure ok (${shimCount} LEGACY-SHIM, ${warnings.length} review warning${warnings.length === 1 ? "" : "s"})`);
