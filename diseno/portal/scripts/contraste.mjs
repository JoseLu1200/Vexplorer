// Contraste WCAG de los tokens sobre los fondos donde caen, en tema claro y oscuro (lee src/styles.css).
// Texto: 4,5:1. Elementos que no son texto (trazos, bordes de control, muestras): 3:1.
import fs from "node:fs";
const css = fs.readFileSync("src/styles.css", "utf8");
const block = (re) => Object.fromEntries([...css.match(re)[1].matchAll(/--([\w-]+):\s*(\d+) (\d+) (\d+)/g)].map((m) => [m[1], [+m[2], +m[3], +m[4]]]));
const light = block(/:root \{([\s\S]*?)\n\}/);
const dark = block(/:root\[data-theme="dark"\] \{([\s\S]*?)\n\}/);
const lum = (c) => c.map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }).reduce((a, v, i) => a + v * [0.2126, 0.7152, 0.0722][i], 0);
const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
const text = [];
// Tinta y grises en los tres fondos: papel (bg), hoja (surface) y papel oscuro (sunken, también la fila seleccionada).
for (const f of ["ink", "muted", "faint", "calc", "hip", "conf", "danger", "cobalt"]) for (const b of ["bg", "surface", "sunken"]) text.push([f, b]);
text.push(["danger", "danger-soft"], ["ink", "danger-soft"], ["unknown-ink", "unknown-bg"], ["dim", "canvas"], ["surface", "ink"], ["wood-ink", "wood"], ["on-block", "block"], ["on-block-2", "block"]);
const shapes = [["canvas-ink", "canvas"], ["line-strong", "surface"], ["line-strong", "bg"], ["select", "canvas"], ["calc", "surface"], ["hip", "surface"], ["conf", "surface"]];
let fails = 0;
for (const [name, t] of [["claro", light], ["oscuro", dark]]) {
  console.log(`== ${name}`);
  for (const [f, b] of text) { const r = ratio(t[f], t[b]); if (r < 4.5) fails++; console.log(`texto  ${f.padEnd(12)} sobre ${b.padEnd(12)} ${r.toFixed(2)} ${r >= 4.5 ? "AA" : "FALLA"}`); }
  for (const [f, b] of shapes) { const r = ratio(t[f], t[b]); if (r < 3) fails++; console.log(`forma  ${f.padEnd(12)} sobre ${b.padEnd(12)} ${r.toFixed(2)} ${r >= 3 ? "3:1" : "FALLA"}`); }
}
console.log(fails ? `\n${fails} pares por debajo del mínimo` : "\nTodos los pares cumplen");
