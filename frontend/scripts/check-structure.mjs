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

// R1/R5/R7 thresholds and domain table (see the pasted structure-rules spec).
const SIZE_THRESHOLD = 8;
const PREFIX_THRESHOLD = 3;
const TEST_FLAT_THRESHOLD = 25;
const MAX_DEPTH_UNDER_LAYER = 2;
const LAYER_ROOTS = new Set(["app", "features", "entities", "shared"]);
const CANONICAL_DOMAINS = new Set([
  "auth", "roster", "topic", "quiz", "mastery", "research", "speaking", "classroom", "shared",
]);
const DOMAIN_KEYWORDS = {
  quiz: "quiz",
  vocabulary: "topic",
  vocab: "quiz",
  story: "topic",
  stories: "topic",
  student: "roster",
  teacher: "roster",
  admin: "roster",
  roster: "roster",
  login: "auth",
  bkt: "mastery",
  srs: "mastery",
  mastery: "mastery",
  research: "research",
  placement: "research",
  speech: "speaking",
  conversation: "speaking",
  speaking: "speaking",
  submit: "speaking",
  help: "classroom",
  audio: "shared",
  media: "shared",
  health: "shared",
};

// Registry of every directory's own files, filled in during visit() and
// consumed once the walk is done (R1/R5/R7 need a full folder listing).
const dirRegistry = new Map();

function relative(file) {
  return path.relative(src, file).replaceAll(path.sep, "/");
}

function leadingWord(baseName) {
  const m = baseName.match(/^[A-Z]?[a-z0-9]+/);
  return (m ? m[0] : baseName).toLowerCase();
}

function findPrefixClusters(stems) {
  const groups = new Map();
  for (const stem of stems) {
    const key = leadingWord(stem);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(stem);
  }
  return [...groups.entries()].filter(([, members]) => members.length >= PREFIX_THRESHOLD);
}

function domainKeywordHits(stem) {
  const lower = stem.toLowerCase();
  const hits = new Set();
  for (const [keyword, domain] of Object.entries(DOMAIN_KEYWORDS)) {
    if (lower.includes(keyword)) hits.add(domain);
  }
  return hits;
}

async function visit(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const rel = relative(directory);
  const record = { sourceFiles: [], testFiles: [], hasSubdirs: false };
  dirRegistry.set(rel, record);

  for (const entry of entries) {
    const fullPath = path.join(directory, entry.name);
    const entryRel = relative(fullPath);
    if (entry.isDirectory()) {
      record.hasSubdirs = true;
      if (directory === src && !allowedTopLevel.has(entry.name)) {
        errors.push(`${entryRel}: src/ contains an unapproved top-level directory`);
      }
      if (entry.name !== "src" && !/^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/.test(entry.name)) {
        errors.push(`${entryRel}: directory names must be kebab-case`);
      }
      await visit(fullPath);
      continue;
    }
    if (!/\.(?:ts|tsx)$/.test(entry.name)) continue;

    const isTest = /\.test\.tsx?$/.test(entry.name);
    const isIndex = entry.name === "index.ts";
    if (isTest) record.testFiles.push(entry.name);
    else if (!isIndex && !entry.name.endsWith(".d.ts")) record.sourceFiles.push(entry.name);

    const text = await readFile(fullPath, "utf8");
    shimCount += (text.match(/LEGACY-SHIM/g) ?? []).length;
    if (/^(?:utils|helpers|misc|common)\.(?:tsx?|jsx?)$/.test(entry.name)) {
      errors.push(`${entryRel}: generic utility filenames are not allowed`);
    }
    if (/^[A-Z]\w*\.[A-Za-z]\w*\.tsx?$/.test(entry.name) && !entry.name.includes(".test.") && !entry.name.endsWith(".d.ts")) {
      errors.push(`${entryRel}: dotted pseudo-folders are not allowed`);
    }
    if (/\bfetch\s*\(/.test(text) && entry.name !== "api.ts" && !entryRel.startsWith("shared/api/")) {
      errors.push(`${entryRel}: fetch() belongs in an api.ts module or shared/api/`);
    }
    const lines = text.split(/\r?\n/).length;
    const limit = entry.name.endsWith(".tsx") ? 250 : 300;
    if (lines >= 500) errors.push(`${entryRel}: ${lines} lines (500-line limit)`);
    else if (lines >= limit) warnings.push(`${entryRel}: ${lines} lines (review at ${limit})`);
  }
}

function checkStructureRules() {
  for (const [rel, record] of dirRegistry) {
    if (rel === "") continue;
    const { sourceFiles, testFiles, hasSubdirs } = record;

    if (sourceFiles.length > SIZE_THRESHOLD) {
      errors.push(
        `R1(b) size: ${rel} has ${sourceFiles.length} source files (threshold ${SIZE_THRESHOLD}): `
        + sourceFiles.slice().sort().join(", ")
      );
    }
    for (const [prefix, members] of findPrefixClusters(sourceFiles.map((f) => f.replace(/\.tsx?$/, "")))) {
      errors.push(
        `R1(a) prefix: ${rel} has ${members.length} files sharing prefix '${prefix}': `
        + members.slice().sort().join(", ")
      );
    }
    if (testFiles.length > TEST_FLAT_THRESHOLD && !hasSubdirs) {
      errors.push(
        `R1(c) flat tests: ${rel} has ${testFiles.length} test files flat with no domain subfolders (threshold ${TEST_FLAT_THRESHOLD})`
      );
    }

    const topLevelName = rel.split("/")[0];
    if (!CANONICAL_DOMAINS.has(topLevelName)) {
      const hitsByDomain = new Map();
      for (const f of sourceFiles) {
        const stem = f.replace(/\.tsx?$/, "");
        for (const domain of domainKeywordHits(stem)) {
          if (!hitsByDomain.has(domain)) hitsByDomain.set(domain, []);
          hitsByDomain.get(domain).push(f);
        }
      }
      for (const [domain, files] of hitsByDomain) {
        errors.push(
          `R7 naming: ${rel} holds ${files.length} file(s) matching domain '${domain}' but the folder isn't named for a canonical domain: `
          + files.slice().sort().join(", ")
        );
      }
    }
  }

  for (const layerName of LAYER_ROOTS) {
    for (const rel of dirRegistry.keys()) {
      if (!rel.startsWith(`${layerName}/`)) continue;
      const depth = rel.split("/").length - 1; // path segments below the layer root
      if (depth > MAX_DEPTH_UNDER_LAYER) {
        errors.push(`R5 depth: ${rel} is ${depth} levels under ${layerName}/ (max ${MAX_DEPTH_UNDER_LAYER})`);
      }
    }
  }
}

await visit(src);
checkStructureRules();
if (shimCount > LEGACY_SHIM_BASELINE) errors.push(`LEGACY-SHIM count is ${shimCount}; baseline allows ${LEGACY_SHIM_BASELINE}`);
for (const warning of warnings) console.warn(`warning: ${warning}`);
for (const error of errors) console.error(`error: ${error}`);
if (errors.length) process.exit(1);
console.log(`structure ok (${shimCount} LEGACY-SHIM, ${warnings.length} review warning${warnings.length === 1 ? "" : "s"})`);
