import { readdir, readFile } from "node:fs/promises";
import { join, relative, resolve } from "node:path";

const root = resolve("src");
const failures = [];

async function visit(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      await visit(path);
      continue;
    }
    const content = await readFile(path, "utf8");
    const lines = content ? content.split(/\r?\n/).length - (content.endsWith("\n") ? 1 : 0) : 0;
    if (lines > 500) failures.push({ path: relative(process.cwd(), path), lines });
  }
}

await visit(root);
failures.sort((a, b) => b.lines - a.lines);
if (failures.length) {
  console.error("Frontend source files must be 500 lines or fewer:");
  for (const failure of failures) console.error(`- ${failure.lines}\t${failure.path}`);
  process.exitCode = 1;
} else {
  console.log("Frontend source line limit: PASS (all files <= 500 lines)");
}
