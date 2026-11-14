// Uso: node scripts/cotas-debug.mjs plank_030,F02
import { build } from "esbuild";
import { mkdtempSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const outfile = path.join(mkdtempSync(path.join(os.tmpdir(), "vexplorer-cotas-")), "cotas.mjs");
await build({ entryPoints: [path.join(here, "cotas-debug.ts")], bundle: true, platform: "node", format: "esm", outfile, logLevel: "warning", define: { "import.meta.env": "{}" } });
await import(pathToFileURL(outfile).href);
