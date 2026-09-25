import { existsSync } from "node:fs";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const name = process.argv[2];
if (!name || !/^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/.test(name)) {
  console.error("Usage: npm run new:feature -- <kebab-case-name>");
  process.exit(1);
}

const pascalName = name.split("-").map((part) => part[0].toUpperCase() + part.slice(1)).join("");
const directory = path.resolve("src/features", name);
if (existsSync(directory)) {
  console.error(`Feature already exists: ${directory}`);
  process.exit(1);
}

await mkdir(directory, { recursive: true });
await writeFile(path.join(directory, "index.ts"), `export { ${pascalName}Page } from "./${pascalName}Page";\n`);
await writeFile(path.join(directory, `${pascalName}Page.tsx`), `import "./${name}.css";\n\nexport function ${pascalName}Page() {\n  return (\n    <main className="${name}-page">\n      <h1>${pascalName}</h1>\n    </main>\n  );\n}\n`);
await writeFile(path.join(directory, `${name}.css`), `.${name}-page {\n  min-height: 100%;\n}\n`);
console.log(`Created feature ${name} in ${path.relative(process.cwd(), directory)}`);
