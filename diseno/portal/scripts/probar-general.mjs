// Empaqueta scripts/probar-general.ts con el esbuild de Vite y lo ejecuta en Node.
// Uso: node scripts/probar-general.mjs [base-backend=http://127.0.0.1:8765] [ruta-vexplorer]
import { build } from "esbuild";
import { mkdtempSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const dir = mkdtempSync(path.join(os.tmpdir(), "vexplorer-probar-"));
const outfile = path.join(dir, "probar-general.mjs");
await build({
  entryPoints: [path.join(here, "probar-general.ts")],
  bundle: true,
  platform: "node",
  format: "esm",
  target: "node20",
  outfile,
  logLevel: "warning",
  // src/api/client.ts lee import.meta.env al cargarse; en Node no existe.
  define: { "import.meta.env": "{}" },
});
try {
  await import(pathToFileURL(outfile).href);
} finally {
  process.on("exit", () => rmSync(dir, { recursive: true, force: true }));
}
