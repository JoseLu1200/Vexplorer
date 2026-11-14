// Capturas del mapa 3D a 1440x900 y 390x844 y medida del tiempo de render durante órbita y zoom.
// Uso: node scripts/mapa_capturas.mjs http://127.0.0.1:5175/src/mapa/demo.html capturas/mapa [filtro]
import { chromium } from "playwright-core";
import fs from "node:fs";

const [, , url = "http://127.0.0.1:5175/src/mapa/demo.html", out = "capturas/mapa", solo = ""] = process.argv;
fs.mkdirSync(out, { recursive: true });
const FIJO = "MH3USCYKTEMTKAABAAAAADQ8_0";
const RARO = "MKG65CQKTECN6AABAAAAADY8_0";

const browser = await chromium.launch({ executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe", headless: true, args: process.env.SWIFTSHADER ? ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] : [] });
const listo = async (p, espacio = "geometria") => {
  await p.waitForFunction((e) => window.__mapa?.listo && window.__mapa.espacio === e, espacio, { timeout: 30000 });
  await p.evaluate(() => document.fonts.ready);
  await p.waitForTimeout(900);
};
const vistas = [
  { tag: "1440", viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 },
  { tag: "390", viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 },
];
const panel = async (p) => {
  await p.waitForSelector("[data-testid=mapa-panel] li svg rect.fill-ink, [data-testid=mapa-panel] li img", { timeout: 10000 });
  await p.waitForTimeout(1200);
};
const tiros = [
  { name: "00-defecto", q: "" },
  { name: "00-defecto-fijado", q: `?foco=${FIJO}`, act: panel },
  { name: "3d-01-general", q: "" },
  { name: "3d-02-hover", q: "", act: async (p) => {
    const ids = await p.evaluate(() => window.__mapa.ids(400));
    for (const id of ids.slice(150)) {
      const pt = await p.evaluate((x) => window.__mapa.pantalla(x), id);
      const izq = p.viewportSize().width >= 640 ? 340 : 20;
      if (!pt || pt.x < izq || pt.y < 300 || pt.x > p.viewportSize().width - 60 || pt.y > p.viewportSize().height - 60) continue;
      await p.mouse.move(pt.x, pt.y, { steps: 3 });
      try { await p.waitForSelector("[data-testid=mapa-hover] svg rect.fill-ink", { timeout: 1500 }); break; } catch { /* siguiente */ }
    }
    await p.waitForTimeout(200);
  } },
  { name: "3d-03-fijado-vecinos", q: `?foco=${FIJO}`, act: panel },
  { name: "3d-04-raro", q: `?foco=${RARO}`, act: panel },
  { name: "3d-05-filtro-familia", q: "", act: async (p) => {
    if (p.viewportSize().width < 640) await p.locator("[data-testid=mapa-leyenda] > button").click();
    await p.locator("[data-testid=mapa-leyenda] li button").nth(5).click();
    await p.waitForTimeout(500);
  } },
  { name: "3d-06-embeddings", q: "?espacio=eg2-mixed-768", espacio: "eg2-mixed-768", act: async (p) => {
    const id = await p.evaluate(() => window.__mapa.ids(30)[12]);
    await p.evaluate((x) => window.__mapa.fijar(x), id);
    await panel(p);
  } },
  { name: "3d-07-cad", q: "?espacio=cad-eg2-logreg373", espacio: "cad-eg2-logreg373" },
  { name: "3d-08-oscuro", q: `?tema=dark&foco=${FIJO}`, act: panel },
];

for (const v of vistas) {
  const ctx = await browser.newContext({ viewport: v.viewport, deviceScaleFactor: v.deviceScaleFactor });
  for (const t of tiros) {
    if (solo && !t.name.includes(solo)) continue;
    const p = await ctx.newPage();
    const errs = [];
    p.on("pageerror", (e) => errs.push(String(e)));
    // Las tomas 3d-* fijan PCA 3D; 00-defecto abre con la proyección por defecto (t-SNE 2D).
    const u = new URL(url + t.q);
    if (t.name.startsWith("3d-")) u.searchParams.set("proyeccion", "pca3");
    await p.goto(u.toString());
    await listo(p, t.espacio);
    if (t.act) await t.act(p);
    await p.screenshot({ path: `${out}/${t.name}-${v.tag}.png` });
    if (errs.length) console.log(t.name, v.tag, errs);
    await p.close();
  }
  await ctx.close();
}

if (!solo || solo === "perf") {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const p = await ctx.newPage();
  await p.goto(url);
  await listo(p);
  console.log("WebGL:", await p.evaluate(() => {
    const g = document.createElement("canvas").getContext("webgl");
    const e = g.getExtension("WEBGL_debug_renderer_info");
    return e ? g.getParameter(e.UNMASKED_RENDERER_WEBGL) : g.getParameter(g.RENDERER);
  }));
  const q = (a, x) => a.slice().sort((m, n) => m - n)[Math.min(a.length - 1, Math.floor(x * a.length))];
  const medir = async (nombre, fn) => {
    await p.evaluate(() => {
      window.__mapa.limpiarTiempos();
      window.__frames = [];
      window.__stop = false;
      let last = performance.now();
      const loop = (t) => { window.__frames.push(t - last); last = t; if (!window.__stop) requestAnimationFrame(loop); };
      requestAnimationFrame(loop);
    });
    await fn();
    const { t, f } = await p.evaluate(() => { window.__stop = true; return { t: window.__mapa.tiempos(), f: window.__frames.slice(2) }; });
    console.log(`${nombre}: ${t.length} renders, CPU mediana ${q(t, 0.5).toFixed(2)} ms, p95 ${q(t, 0.95).toFixed(2)} ms · ${f.length} frames, intervalo mediana ${q(f, 0.5).toFixed(1)} ms, p95 ${q(f, 0.95).toFixed(1)} ms`);
  };
  await medir("órbita", async () => {
    await p.mouse.move(800, 450);
    await p.mouse.down();
    for (let k = 0; k < 200; k++) await p.mouse.move(800 + 300 * Math.sin(k / 25), 450 + 120 * Math.cos(k / 31));
    await p.mouse.up();
  });
  await medir("zoom", async () => {
    await p.mouse.move(800, 450);
    for (let k = 0; k < 60; k++) { await p.mouse.wheel(0, k < 30 ? -100 : 100); await p.waitForTimeout(16); }
  });
  await medir("hover", async () => {
    for (let k = 0; k < 200; k++) await p.mouse.move(500 + k * 3, 300 + 200 * Math.sin(k / 15));
  });
  await ctx.close();
}
await browser.close();
