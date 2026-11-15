// Capturas de todas las pantallas a 1440x900 y 390x844 con el Chrome instalado (playwright-core, sin descargar navegadores).
// Uso: node scripts/capturas.mjs http://127.0.0.1:4417/ capturas/sistema [filtro]
// Cada captura abre un contexto nuevo: IndexedDB vacía y espacio de trabajo sembrado con los seis DXF de ejemplo.
import { chromium } from "playwright-core";
import fs from "node:fs";

const [, , base = "http://127.0.0.1:4417/", out = "capturas/sistema", filter = ""] = process.argv;
fs.mkdirSync(out, { recursive: true });
const dxf = (name) => fs.readFileSync(`src/assets/dxf/${name}`);

const ready = async (p) => {
  await p.waitForSelector("[data-testid=boot]", { state: "detached", timeout: 15000 });
  await p.waitForFunction(() => document.querySelectorAll("[data-plan]").length >= 6 && !document.querySelector("[data-plan][data-status=analyzing]"), null, { timeout: 20000 });
};
const openPlan = async (p, name) => {
  await p.locator(`[data-plan] button[aria-label^='${name}']`).first().click();
  await p.waitForSelector("[aria-label='Clases de dato'] >> visible=true", { timeout: 20000 });
};
const dropFiles = async (p, selector, files, release = true) => {
  const payload = files.map((f) => ({ name: f.name, type: f.type, b64: f.buffer.toString("base64") }));
  const dt = await p.evaluateHandle((list) => {
    const transfer = new DataTransfer();
    for (const f of list) transfer.items.add(new File([Uint8Array.from(atob(f.b64), (c) => c.charCodeAt(0))], f.name, { type: f.type }));
    return transfer;
  }, payload);
  await p.dispatchEvent(selector, "dragover", { dataTransfer: dt });
  if (release) await p.dispatchEvent(selector, "drop", { dataTransfer: dt });
};
const wide = (p) => p.viewportSize().width >= 1024;

const shots = [
  { name: "01-arranque", q: "", wait: "[data-testid=boot]", delay: 480, noBlur: true },
  { name: "02-planos", q: "", ready: true },
  { name: "03-carpeta", q: "", ready: true, act: async (p) => {
    await p.locator(wide(p) ? "aside button:has-text('Serie E-900')" : "[role=listitem]:has-text('Serie E-900')").first().click();
    await p.waitForTimeout(300);
  } },
  { name: "04-busqueda", q: "", ready: true, act: async (p) => { await p.fill("#plan-search", "qty"); await p.waitForTimeout(200); } },
  { name: "05-busqueda-sin-resultados", q: "", ready: true, act: async (p) => { await p.fill("#plan-search", "armario"); await p.waitForTimeout(200); } },
  { name: "06-carpeta-nueva-vacia", q: "", ready: true, act: async (p) => {
    await p.locator("button:has-text('Nueva carpeta') >> visible=true").first().click();
    await p.fill("#name-field", "Presupuestos 2026");
    await p.locator("[role=dialog] button:has-text('Guardar')").click();
    await p.waitForSelector("text=Esta carpeta está vacía");
  }, delay: 1400 },
  { name: "07-dialogo-mover", q: "", ready: true, act: async (p) => {
    await p.locator("[data-plan] [aria-haspopup=menu]").first().click();
    await p.waitForTimeout(150);
    await p.locator("[role=menuitem]:has-text('Mover a otra carpeta')").click();
    await p.waitForSelector("[role=dialog]");
  }, noBlur: true },
  { name: "08-menu-plano", q: "", ready: true, act: async (p) => {
    await p.locator("[data-plan] [aria-haspopup=menu]").nth(2).click();
    await p.waitForSelector("[role=menu]");
  }, noBlur: true },
  { name: "09-arrastre-sobre-carpeta", q: "", ready: true, act: async (p) => {
    const sel = wide(p) ? "aside [data-drop-folder]:has-text('Serie E-1000')" : "[role=listitem]:has-text('Serie E-1000')";
    await dropFiles(p, sel, [{ name: "estanteria_salon.dxf", type: "application/dxf", buffer: dxf("piezas_completo.dxf") }, { name: "estanteria_pasillo.dxf", type: "application/dxf", buffer: dxf("piezas_qty_desconocida.dxf") }], false);
    await p.waitForSelector("[data-testid=drop-overlay]");
  }, noBlur: true },
  { name: "10-cola-en-curso", q: "", ready: true, act: async (p) => {
    await dropFiles(p, "main", [
      { name: "estanteria_salon.dxf", type: "application/dxf", buffer: dxf("piezas_completo.dxf") },
      { name: "estanteria_pasillo.dxf", type: "application/dxf", buffer: dxf("piezas_qty_desconocida.dxf") },
      { name: "estanteria_taller.dxf", type: "application/dxf", buffer: dxf("piezas_espesor_desconocido.dxf") },
      { name: "plano-conjunto.pdf", type: "application/pdf", buffer: Buffer.from("%PDF-1.4\n%") },
    ]);
    await p.waitForSelector("[data-testid=queue-item][data-stage=running], [data-testid=queue-item][data-stage=tracing]", { timeout: 8000 });
  }, delay: 250 },
  { name: "11-cola-terminada", q: "", ready: true, act: async (p) => {
    await dropFiles(p, "main", [
      { name: "estanteria_salon.dxf", type: "application/dxf", buffer: dxf("piezas_completo.dxf") },
      { name: "estanteria_pasillo.dxf", type: "application/dxf", buffer: dxf("piezas_qty_desconocida.dxf") },
      { name: "plano-conjunto.pdf", type: "application/pdf", buffer: Buffer.from("%PDF-1.4\n%") },
    ]);
    await p.waitForFunction(() => [...document.querySelectorAll("[data-testid=queue-item]")].every((el) => ["done", "error"].includes(el.getAttribute("data-stage"))), null, { timeout: 30000 });
  }, delay: 5200 },
  { name: "12-analisis-en-curso-asistente", q: "auto=principal&mode=live&go=analisis", wait: "text=Inspeccionar pieza K2", delay: 120 },
  { name: "13-analisis-terminado", q: "auto=principal&mode=live&go=analisis", wait: "text=Análisis terminado", delay: 900 },
  { name: "14-error-de-formato", q: "", ready: true, act: async (p) => {
    await dropFiles(p, "main", [{ name: "plano-conjunto.pdf", type: "application/pdf", buffer: Buffer.from("%PDF-1.4\n%") }]);
    await p.waitForSelector("[data-plan][data-status=error]", { timeout: 8000 });
    await p.locator("[data-plan][data-status=error] button").first().click();
    await p.waitForSelector("[role=alert]");
  }, delay: 5000 },
  { name: "15-esqueleto-al-abrir", q: "", ready: true, act: async (p) => {
    // Tras recargar, el mock ya no tiene el análisis: el plano se vuelve a analizar con el DXF guardado.
    await openPlan(p, "piezas_espesor_desconocido.dxf");
    await p.reload();
    await p.waitForSelector("[data-testid=boot]", { state: "detached", timeout: 15000 });
    await p.waitForSelector("[data-testid=plan-skeleton]", { timeout: 5000 });
  }, delay: 300 },
  { name: "16-plano-hover", q: "", ready: true, act: async (p) => {
    await openPlan(p, "piezas_espesor_desconocido.dxf");
    if (wide(p)) await p.locator("tr[data-row]").first().hover();
    else await p.locator("[data-contour='contour-entity-8D']").click({ force: true });
  }, noBlur: true },
  { name: "17-plano-medir", q: "", ready: true, act: async (p) => {
    await openPlan(p, "piezas_espesor_desconocido.dxf");
    await p.locator("button[title^='Medir']").click();
    const k1 = await p.locator("[data-contour='contour-entity-8D']").boundingBox();
    await p.mouse.click(k1.x + 1, k1.y + k1.height - 1);
    await p.mouse.click(k1.x + k1.width - 1, k1.y + 1);
    await p.mouse.move(k1.x + k1.width + 40, k1.y - 30);
  }, noBlur: true },
  { name: "18-plano-capas", q: "", ready: true, act: async (p) => {
    await openPlan(p, "piezas_espesor_desconocido.dxf");
    await p.locator("button[title='Capas']").click();
    await p.locator("label:has-text('Cotas') input").uncheck();
  }, noBlur: true },
  { name: "19-plano-completar", q: "", ready: true, sheet: true, act: async (p) => {
    await openPlan(p, "piezas_espesor_desconocido.dxf");
    if (wide(p)) await p.locator("tr[data-row] button:has-text('desconocido')").first().click();
    else { await p.locator("li button:has-text('K3')").first().click(); await p.locator("button:has-text('Ver detalle')").click(); }
    await p.locator("[id^=inline-thickness] >> visible=true").fill("18");
    await p.locator("[id^=inline-reason] >> visible=true").fill("Grosor confirmado con compras");
    await p.locator("[id^=inline-reviewer] >> visible=true").fill("L. Ferrer");
  }, noBlur: true },
  { name: "20-plano-revision-desde-despiece", q: "", ready: true, sheet: true, act: async (p) => {
    await openPlan(p, "piezas_espesor_desconocido.dxf");
    if (wide(p)) await p.locator("tr[data-row] button:has-text('desconocido')").first().click();
    else { await p.locator("li button:has-text('K3')").first().click(); await p.locator("button:has-text('Ver detalle')").click(); }
    await p.locator("[id^=inline-thickness] >> visible=true").fill("18");
    await p.locator("[id^=inline-reason] >> visible=true").fill("Grosor confirmado con compras");
    await p.locator("[id^=inline-reviewer] >> visible=true").fill("L. Ferrer");
    await p.locator("button:has-text('Crear revisión 2') >> visible=true").click();
    await p.waitForSelector("text=Revisión 2 guardada", { timeout: 8000 });
  }, noBlur: true },
  { name: "21-abrir-en-cad", q: "", ready: true, act: async (p) => {
    await openPlan(p, "piezas_espesor_desconocido.dxf");
    if (wide(p)) await p.locator("[aria-label='Opciones de CAD']").first().click();
  }, noBlur: true },
  { name: "22-ficha-biblioteca", q: "", ready: true, act: async (p) => {
    await p.locator("[data-plan] button[aria-label^='piezas_espesor_36']").first().click();
    await p.waitForSelector("text=Guardado en la biblioteca", { timeout: 10000 });
  } },
  { name: "23-atajos", q: "", ready: true, act: async (p) => { await p.keyboard.press("?"); await p.waitForSelector("[role=dialog]"); }, noBlur: true, only: "1440" },
  { name: "24-revision-r2", q: "auto=principal&review=18&go=revision", wait: "text=Historial" },
  { name: "25-esquema-r2", q: "auto=principal&review=18&go=esquema&sel=K3", wait: "canvas", delay: 1200 },
  { name: "26-similares", q: "auto=principal&review=18&save=1&go=similares", wait: "text=Similares en la biblioteca", delay: 800 },
  { name: "27-compras", q: "auto=principal&review=18&estimate=1&go=compras", wait: "text=Total provisional >> visible=true" },
  { name: "28-oscuro-planos", q: "theme=dark", ready: true },
  { name: "29-oscuro-plano-medir", q: "theme=dark", ready: true, act: async (p) => {
    await openPlan(p, "piezas_espesor_desconocido.dxf");
    if (wide(p)) await p.locator("tr[data-row]").nth(3).click();
    await p.locator("button[title^='Medir']").click();
    const k1 = await p.locator("[data-contour='contour-entity-8D']").boundingBox();
    await p.mouse.click(k1.x + 1, k1.y + k1.height - 1);
    await p.mouse.click(k1.x + k1.width - 1, k1.y + k1.height - 1);
  }, noBlur: true },
  { name: "30-oscuro-analisis", q: "auto=principal&mode=live&go=analisis&theme=dark", wait: "text=Análisis terminado", delay: 900 },
  { name: "31-oscuro-cola", q: "theme=dark", ready: true, act: async (p) => {
    await dropFiles(p, "main", [
      { name: "estanteria_salon.dxf", type: "application/dxf", buffer: dxf("piezas_completo.dxf") },
      { name: "plano-conjunto.pdf", type: "application/pdf", buffer: Buffer.from("%PDF-1.4\n%") },
    ]);
    await p.waitForFunction(() => [...document.querySelectorAll("[data-testid=queue-item]")].every((el) => ["done", "error"].includes(el.getAttribute("data-stage"))), null, { timeout: 30000 });
  }, delay: 5200 },
  { name: "32-oscuro-ficha-biblioteca", q: "theme=dark", ready: true, act: async (p) => {
    await p.locator("[data-plan] button[aria-label^='piezas_dimensiones_variante']").first().click();
    await p.waitForSelector("text=Guardado en la biblioteca", { timeout: 10000 });
  } },
];

const browser = await chromium.launch({
  executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  headless: true,
  args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
});
const report = [];
for (const shot of shots.filter((s) => s.name.includes(filter))) {
  for (const [vp, width, height] of [["1440", 1440, 900], ["390", 390, 844]]) {
    if (shot.only && shot.only !== vp) continue;
    const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1, acceptDownloads: true });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
    await page.goto(`${base}${shot.q ? `?${shot.q}` : ""}`, { waitUntil: "load" });
    try {
      if (shot.ready) await ready(page);
      if (shot.wait) await page.waitForSelector(shot.wait, { timeout: 20000 });
      if (shot.q.includes("sel=")) await page.waitForSelector("tr[aria-selected=true]:visible, button[aria-pressed=true]:visible", { timeout: 8000 });
      if (shot.act) await shot.act(page);
      // El aviso de la revisión creada por el autopiloto taparía la pantalla capturada.
      if (shot.q.includes("review=")) await page.locator("[aria-label='Cerrar aviso']").click({ timeout: 2000 }).catch(() => {});
      if (!shot.noBlur) await page.evaluate(() => { document.activeElement?.blur?.(); });
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.waitForTimeout(shot.delay ?? 400);
    } catch (e) {
      errors.push(`paso fallido: ${String(e.message).split("\n")[0]}`);
    }
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
    const file = `${out}/${shot.name}-${vp}.png`;
    // La hoja inferior del móvil es fija: a página completa quedaría en mitad de la captura.
    await page.screenshot({ path: file, fullPage: !(shot.sheet && vp === "390") });
    report.push(`${file}${overflow ? " SCROLL-HORIZONTAL" : ""}${errors.length ? ` ERRORES: ${errors.join(" | ")}` : ""}`);
    await context.close();
  }
}
await browser.close();
console.log(report.join("\n"));
