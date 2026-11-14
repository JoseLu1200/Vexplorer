// Capturas del portal (mesa de trabajo) a 1440x900 y 390x844 con el Chrome instalado (playwright-core).
// Uso: node scripts/portal.mjs http://127.0.0.1:5175/ capturas/portal [filtro]
// Cada captura abre un contexto nuevo: IndexedDB vacía y espacio de trabajo sembrado, sin tocar el navegador de nadie.
// Comprueba además el scroll horizontal de cada captura y lo escribe en la consola.
import { chromium } from "playwright-core";
import fs from "node:fs";

const [, , base = "http://127.0.0.1:5175/", out = "capturas/portal", filter = ""] = process.argv;
fs.mkdirSync(out, { recursive: true });

const ready = async (p) => {
  await p.waitForSelector("[data-testid=boot]", { state: "detached", timeout: 15000 });
  await p.waitForFunction(() => document.querySelectorAll("[data-plan]").length >= 6 && !document.querySelector("[data-plan][data-status=analyzing]"), null, { timeout: 20000 });
};
const openPlan = async (p, name = "piezas_espesor_desconocido") => {
  await p.locator(`[data-plan] button[aria-label^='${name}']`).first().click();
  await p.waitForSelector("[data-testid=workbench]", { timeout: 20000 });
  await p.waitForTimeout(400);
};
const wide = (p) => p.viewportSize().width >= 1024;
const view = async (p, label) => { await p.locator(`[data-testid=view-switch] button:has-text('${label}')`).click(); await p.waitForTimeout(500); };
const pickRow = async (p, key, nth = 0) => {
  if (!wide(p)) await p.locator("[data-testid=workbench] button[aria-expanded]").last().click();
  await p.locator(`[data-row]:has(span:text-is('${key}'))`).nth(nth).click();
  await p.waitForTimeout(350);
};

const shots = [
  // Fase 1: mesa de trabajo
  { name: "p1-mesa-limpio", plan: true },
  { name: "p1-mesa-original", plan: true, act: (p) => view(p, "Original") },
  { name: "p1-mesa-piezas", plan: true, act: (p) => view(p, "Piezas") },
  { name: "p1-mesa-3d-sin-montaje", plan: true, act: (p) => view(p, "3D"), delay: 900 },
  { name: "p1-mesa-3d-r2", q: "auto=principal&review=18&go=esquema", wait: "[data-testid=workbench]", delay: 1500 },
  { name: "p1-ficha-pieza", plan: true, act: (p) => pickRow(p, "K3") },
  { name: "p1-ficha-plegada", plan: true, wideOnly: true, act: async (p) => { await p.locator("button[aria-label='Plegar ficha']").click(); await p.waitForTimeout(400); } },
  { name: "p1-panel-revision", plan: true, act: async (p) => { await p.evaluate(() => { location.hash = location.hash.replace(/\/[a-z]+$/, "/revision"); }); await p.waitForTimeout(600); } },
  // Fase 2: selección e iluminación cruzada
  { name: "p2-hover-contorno", plan: true, wideOnly: true, keepMouse: true, act: async (p) => { await p.locator("[data-contour]").nth(1).hover(); await p.waitForTimeout(250); } },
  { name: "p2-hover-lista", plan: true, wideOnly: true, keepMouse: true, act: async (p) => { await p.locator("[data-row]").nth(1).hover(); await p.waitForTimeout(250); } },
  { name: "p2-seleccion-a-piezas", plan: true, act: async (p) => { await pickRow(p, "K2"); await view(p, "Piezas"); } },
  { name: "p2-seleccion-3d", q: "auto=principal&review=18&go=esquema&sel=K3", wait: "[data-testid=ficha]", delay: 1500 },
  { name: "p2-3d-a-plano", q: "auto=principal&review=18&go=esquema&sel=K1", wait: "[data-testid=ficha]", delay: 900, act: (p) => view(p, "Limpio") },
  { name: "p2-contorno-de-ficha", plan: true, wideOnly: true, keepMouse: true, act: async (p) => { await pickRow(p, "K1"); await p.locator("[data-testid=ficha] button:has-text('Perfil')").hover(); await p.waitForTimeout(250); } },
  { name: "p2-centrar", plan: true, act: async (p) => { await pickRow(p, "K1"); await p.locator("[data-testid=ficha] button:has-text('Centrar')").click(); await p.waitForTimeout(400); } },
  // Fase 3: pasos y bloques de acciones
  { name: "p3-pasos", plan: true },
  { name: "p3-bloque-salidas", plan: true, wideOnly: true, act: (p) => openMenu(p, "Salidas") },
  { name: "p3-bloque-revision", plan: true, wideOnly: true, act: (p) => openMenu(p, "Revisión") },
  { name: "p3-bloque-mas", plan: true, wideOnly: true, act: (p) => openMenu(p, "Más") },
  { name: "p3-acciones-movil", plan: true, act: async (p) => { if (wide(p)) return; await p.locator("button[aria-label='Acciones']").click(); await p.waitForSelector("[role=menu]"); } },
  { name: "p3-completar", plan: true, act: async (p) => { await menuItem(p, "Revisión", "Completar desconocidos"); await p.waitForTimeout(400); } },
  { name: "p3-coste", q: "auto=principal&review=18&estimate=1&go=compras", wait: "[role=dialog]", delay: 1200 },
  { name: "p3-presupuesto", q: "auto=principal&review=18&estimate=1&go=presupuesto", wait: "[role=dialog]", delay: 1200, act: async (p) => { await p.locator("[role=dialog] button:has-text('Exportar CSV')").click(); await p.waitForTimeout(600); } },
  { name: "p3-similares", q: "auto=principal&review=18&go=similares", wait: "[role=dialog]", delay: 1500 },
  // Fase 4: entrada con carpetas
  { name: "p4-entrada", home: true },
  { name: "p4-carpeta", home: true, act: async (p) => { await p.locator(wide(p) ? "aside button:has-text('Serie E-900')" : "[role=listitem]:has-text('Serie E-900')").first().click(); await p.waitForTimeout(300); } },
  { name: "p4-modo-de-subida", home: true, act: async (p) => { await p.locator("button[aria-label='Modo de análisis']").click(); await p.waitForSelector("[role=menu]"); } },
  { name: "p4-plano-de-biblioteca", home: true, act: async (p) => { await p.locator("[data-plan] button[aria-label^='piezas_completo']").first().click(); await p.waitForSelector("[data-testid=workbench]"); await p.waitForTimeout(600); } },
  { name: "p4-analisis-en-curso", q: "auto=principal&mode=live&go=analisis", wait: "text=Análisis terminado", delay: 600 },
  { name: "p4-oscuro-mesa", q: "theme=dark", plan: true, act: (p) => pickRow(p, "K1") },
  { name: "p2-ambigua-seleccion", plan: true, planName: "piezas_ambigua_sin_id", act: async (p) => { await p.locator("[data-contour]").first().click(); await p.waitForTimeout(400); } },
  // Comprobaciones finales
  { name: "z-centrar-desde-piezas", plan: true, act: async (p) => { await view(p, "Piezas"); await pickRow(p, "K1"); await p.locator("[data-testid=ficha] button:has-text('Centrar')").click(); await p.waitForTimeout(700); } },
  { name: "z-laminas-impresion", plan: true, wideOnly: true, act: async (p) => { await view(p, "Piezas"); await p.emulateMedia({ media: "print" }); await p.waitForTimeout(300); }, fullPage: true },
];
async function openMenu(p, label) { await p.locator(`[data-testid=action-blocks] button[aria-label='${label}']`).click(); await p.waitForSelector("[role=menu]"); }
async function menuItem(p, block, label) {
  if (wide(p)) await openMenu(p, block); else { await p.locator("button[aria-label='Acciones']").click(); await p.waitForSelector("[role=menu]"); }
  await p.locator(`[role=menuitem]:has-text('${label}')`).click();
}

const browser = await chromium.launch({ executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe", headless: true });
for (const shot of shots.filter((item) => item.name.includes(filter))) {
  for (const width of [1440, 390]) {
    if (shot.wideOnly && width < 1024) continue;
    const ctx = await browser.newContext({ viewport: { width, height: width === 390 ? 844 : 900 }, deviceScaleFactor: 1 });
    const p = await ctx.newPage();
    const errors = [];
    p.on("pageerror", (error) => errors.push(error.message));
    try {
      await p.goto(`${base}${shot.q ? `?${shot.q}` : ""}`);
      if (shot.plan) { await ready(p); await openPlan(p, shot.planName); }
      if (shot.home) await ready(p);
      if (shot.wait) await p.waitForSelector(shot.wait, { timeout: 20000 });
      if (shot.act) await shot.act(p);
      await p.waitForTimeout(shot.delay ?? 300);
      // Los avisos breves tapan el contenido: se cierran antes de la captura.
      for (const close of await p.locator("[aria-label='Cerrar aviso']").all()) await close.click().catch(() => {});
      if (!shot.keepMouse) await p.mouse.move(1, 1);
      const file = `${out}/${shot.name}-${width}.png`;
      await p.screenshot({ path: file, fullPage: !!shot.fullPage });
      const overflow = await p.evaluate(() => document.documentElement.scrollWidth - innerWidth);
      console.log(`${file}${overflow > 0 ? `  SCROLL HORIZONTAL ${overflow}px` : ""}${errors.length ? `  ERRORES ${errors.join(" | ")}` : ""}`);
    } catch (error) {
      console.log(`${shot.name}-${width} FALLO ${error.message.split("\n")[0]}`);
    }
    await ctx.close();
  }
}
await browser.close();
