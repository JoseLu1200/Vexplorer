// Recorrido completo contra el backend real (VITE_USE_MOCK=false, mismo origen).
// Adaptado al espacio de trabajo: se sube el DXF desde Planos y se abre desde la cola. Sin volver a ejecutar contra el backend.
// Uso: node scripts/backend-real.mjs http://127.0.0.1:4391/ <ruta-a-data/planos_demo> capturas/backend-real
import { chromium } from "playwright-core";
import fs from "node:fs";
import path from "node:path";

const [, , base, demoDir, out] = process.argv;
fs.mkdirSync(out, { recursive: true });
const browser = await chromium.launch({ executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe", headless: true, args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const log = [];
page.on("pageerror", (e) => log.push(`pageerror ${e.message}`));
page.on("response", (r) => { if (r.url().includes("/api/v1/")) log.push(`${r.request().method()} ${new URL(r.url()).pathname}${new URL(r.url()).search} ${r.status()}`); });
const shot = async (name) => { await page.evaluate(() => window.scrollTo(0, 0)); await page.screenshot({ path: `${out}/${name}.png`, fullPage: true }); };
const LABELS = { revision: "Revisión", esquema: "Esquema", compras: "Compras", similares: "Similares" };
const nav = (id) => page.locator(`nav[aria-label='Pantallas del plano'] a:has-text('${LABELS[id]}'):visible`).first().click();

await page.goto(base);
await page.waitForSelector("[data-testid=boot]", { state: "detached", timeout: 15000 });
await page.waitForSelector("text=Subir DXF");
// Sin proveedor configurado, «Con asistente IA» debe aparecer deshabilitado con su motivo.
await shot("01-planos-backend-real");
await page.setInputFiles("#dxf-files", path.join(demoDir, "piezas_espesor_desconocido.dxf"));
await page.waitForSelector("[data-testid=queue-item][data-stage=done]", { timeout: 30000 });
await page.locator("[data-testid=queue-item] button:has-text('Ver')").first().click();
await page.waitForSelector("table");
await page.locator("tr:visible", { hasText: "K3" }).first().click();
await page.waitForTimeout(500);
await shot("03-plano-r1-backend-real");
await page.locator("nav[aria-label='Pantallas del plano'] a:has-text('Análisis'):visible").first().click();
await page.waitForSelector("text=Análisis terminado", { timeout: 15000 });
await shot("02-traza-backend-real");
await page.locator("nav[aria-label='Pantallas del plano'] a:has-text('Plano'):visible").first().click();
await page.waitForSelector("table");

await nav("revision");
await page.waitForSelector("text=Correcciones");
await page.locator("[id^=edit-][id*=thickness]:visible").first().fill("18");
await page.locator("[id^=reason-use-part-observation-k3]:visible").first().fill("Grosor confirmado con compras");
await page.fill("#reviewer", "L. Ferrer");
await page.selectOption("#material", "tablero sintético");
await page.selectOption("#finish", "melamina sintética");
await page.fill("#note", "Montaje entre laterales revisado");
await page.click("text=Crear revisión 2");
await page.waitForSelector("text=Revisión 2 guardada", { timeout: 15000 });
await shot("04-revision-r2-backend-real");

await nav("esquema");
await page.waitForSelector("canvas", { timeout: 15000 });
await page.waitForTimeout(1200);
await shot("05-esquema-backend-real");

await nav("compras");
await page.click("text=Calcular estimación");
await page.waitForSelector("text=Total provisional >> visible=true", { timeout: 15000 });
await page.click("button:has-text('CSV')");
await page.waitForSelector("pre", { timeout: 15000 });
await shot("06-compras-backend-real");

await nav("similares");
await page.fill("#lib-label", "Estantería E-900 cuatro baldas");
await page.click("form:has(#lib-label) button");
await page.waitForSelector("text=En la biblioteca", { timeout: 15000 });
await page.waitForTimeout(800);
await shot("07-similares-backend-real");

fs.writeFileSync(`${out}/registro-http.txt`, log.join("\n") + "\n");
console.log(log.join("\n"));
await browser.close();
