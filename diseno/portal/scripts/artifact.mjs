// Adapta dist-single/index.html al contrato de Artifact: sin doctype, html, head ni body propios.
// Conserva <title>, metas, icono, estilos y scripts, y el contenedor #root. Escribe dist-single/vexplorer-app.html.
import fs from "node:fs";

const html = fs.readFileSync("dist-single/index.html", "utf8");
const head = html.match(/<head>([\s\S]*?)<\/head>/i)?.[1] ?? "";
const body = html.match(/<body>([\s\S]*?)<\/body>/i)?.[1] ?? "";
const keep = head
  .replace(/<meta charset="[^"]*"\s*\/?>/i, "")
  .replace(/<meta name="viewport"[^>]*>/i, "");
const title = keep.match(/<title>[\s\S]*?<\/title>/i)?.[0] ?? "<title>Vexplorer</title>";
const meta = keep.match(/<meta name="claude:viewport-fit-sides"[^>]*>/i)?.[0] ?? "";
const rest = keep.replace(title, "").replace(meta, "");
// El script de módulo va al final para que #root exista cuando se ejecute.
const scripts = [...rest.matchAll(/<script[\s\S]*?<\/script>/gi)].map((m) => m[0]);
const others = scripts.reduce((acc, s) => acc.replace(s, ""), rest);
const out = `${title}\n${meta}\n${others.trim()}\n${body.trim()}\n${scripts.join("\n")}\n`;
fs.writeFileSync("dist-single/vexplorer-app.html", out);
const size = Buffer.byteLength(out);
const external = [...out.matchAll(/url\((?!["']?data:)[^)]*\)/g)].map((m) => m[0]).filter((u) => !u.includes("#"));
console.log(`vexplorer-app.html ${(size / 1024).toFixed(0)} KiB · url() no inline: ${external.length ? external.slice(0, 5).join(", ") : "ninguna"}`);
