// Capturas de cada proyección (PCA 3D, UMAP 2D, t-SNE 2D) del espacio geométrico y de EG2 mixto 768 a 1440x900.
// Cambia de proyección con el control segmentado, como un usuario; comprueba que el fijado se mantiene.
// Uso: node scripts/mapa_proyecciones_capturas.mjs http://127.0.0.1:5175/src/mapa/demo.html capturas/mapa/proyecciones
import { chromium } from "playwright-core";
import fs from "node:fs";

const [, , url = "http://127.0.0.1:5175/src/mapa/demo.html", out = "capturas/mapa/proyecciones"] = process.argv;
fs.mkdirSync(out, { recursive: true });
const b = await chromium.launch({ executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe", headless: true });
const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
for (const [espacio, q] of [["geometria", ""], ["eg2-mixed-768", "?espacio=eg2-mixed-768"]]) {
  const p = await ctx.newPage();
  const errs = [];
  p.on("pageerror", (e) => errs.push(String(e)));
  await p.goto(url + q);
  await p.waitForFunction((e) => window.__mapa?.listo && window.__mapa.espacio === e, espacio);
  await p.waitForSelector("[data-testid=mapa-proyeccion] button", { timeout: 15000 });
  await p.evaluate(() => document.fonts.ready);
  const botones = await p.locator("[data-testid=mapa-proyeccion] button").allTextContents();
  for (const [k, nombre] of botones.entries()) {
    await p.locator("[data-testid=mapa-proyeccion] button").nth(k).click();
    await p.waitForTimeout(1300);
    const f = `${out}/${espacio}-${String(k + 1).padStart(2, "0")}-${nombre.replace(/[^A-Za-z0-9]+/g, "-").toLowerCase()}-1440.png`;
    await p.screenshot({ path: f });
    console.log(f);
  }
  // Fijado y filtro se mantienen al cambiar de proyección.
  const id = await p.evaluate(() => window.__mapa.ids(50)[20]);
  await p.evaluate((x) => window.__mapa.fijar(x), id);
  await p.locator("[data-testid=mapa-leyenda] li button").first().click();
  await p.waitForTimeout(900);
  await p.locator("[data-testid=mapa-proyeccion] button").first().click();
  await p.waitForTimeout(1300);
  const panel = await p.locator("[data-testid=mapa-panel] header .break-all").textContent().catch(() => null);
  const filtro = await p.locator("[data-testid=mapa-leyenda] li button[aria-pressed=true]").count();
  await p.screenshot({ path: `${out}/${espacio}-fijado-tras-cambio-1440.png` });
  console.log(espacio, "fijado", id === panel ? "se mantiene" : `CAMBIA (${panel})`, "· filtro activo", filtro, errs.length ? errs : "");
  await p.close();
}
await b.close();
