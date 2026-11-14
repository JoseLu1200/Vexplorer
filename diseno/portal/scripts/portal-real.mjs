// Recorrido del portal contra el backend real (vite en modo real, p. ej. http://127.0.0.1:5176/).
// Uso: node scripts/portal-real.mjs http://127.0.0.1:5176/ <DXF de piezas separadas> [carpeta de capturas] [DXF de mueble general]
// Sube el DXF, espera al análisis, abre la mesa, recorre las cuatro vistas, selecciona una pieza y abre los paneles.
// Escribe los errores de consola y cada respuesta /api con estado >= 400.
import { chromium } from "playwright-core";
import fs from "node:fs";

const [, , base = "http://127.0.0.1:5176/", dxf, out = "", general = ""] = process.argv;
if (out) fs.mkdirSync(out, { recursive: true });
const browser = await chromium.launch({ executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe", headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const p = await ctx.newPage();
const problems = [];
const calls = [];
p.on("console", (msg) => { if (msg.type() === "error") problems.push(`consola: ${msg.text()}`); });
p.on("pageerror", (error) => problems.push(`excepción: ${error.message}`));
p.on("response", (res) => {
  const url = new URL(res.url());
  if (!url.pathname.startsWith("/api")) return;
  calls.push(`${res.request().method()} ${url.pathname}${url.search} ${res.status()}`);
  if (res.status() >= 400) problems.push(`api ${res.status()}: ${res.request().method()} ${url.pathname}${url.search}`);
});
const shot = async (name) => { if (out) await p.screenshot({ path: `${out}/${name}.png` }); };
const step = async (label, fn) => { try { await fn(); console.log(`ok   ${label}`); } catch (error) { problems.push(`${label}: ${error.message.split("\n")[0]}`); console.log(`FALLO ${label}`); } };

await p.goto(base);
await p.waitForSelector("[data-testid=boot]", { state: "detached", timeout: 15000 });
// Carpeta «Muebles procesados»: los RUNS_DEMO se abren del servidor con abrirRun y F01, F02 y F03 desde src/casos.
await step("muebles procesados sembrados", async () => {
  await p.waitForFunction(() => [...document.querySelectorAll("[data-plan]")].some((el) => el.textContent.includes("Cajonera")), null, { timeout: 30000 });
  await shot("real-entrada");
});
// Navegadores con datos guardados: si la marca de la siembra desaparece, la carpeta no se duplica.
await step("siembra sin duplicados", async () => {
  await p.waitForTimeout(500);
  await p.evaluate(() => localStorage.removeItem("vx-muebles-procesados"));
  await p.reload();
  await p.waitForSelector("[data-testid=boot]", { state: "detached", timeout: 15000 });
  await p.waitForTimeout(2500);
  const counts = await p.evaluate(() => ({ cases: [...document.querySelectorAll("[data-plan]")].filter((el) => /Cajonera|Estantería|Mesa con|Mueble bajo|Control con/.test(el.textContent)).length }));
  console.log(`     tarjetas de Muebles procesados: ${counts.cases}`);
  if (counts.cases !== 7) throw new Error(`se esperaban 7 y hay ${counts.cases}`);
});
for (const demo of ["Estantería de 900 mm", "Control con espesor desconocido", "Cajonera de tres cajones"]) {
  await step(`abrir ${demo}`, async () => {
    await p.locator(`[data-plan] button[aria-label^='${demo}']`).first().click();
    await p.waitForSelector("[data-testid=workbench]", { timeout: 30000 });
    await p.waitForTimeout(900);
    if (await p.locator("[data-row]").count()) { await p.locator("[data-row]").first().click(); await p.waitForTimeout(500); }
    const slug = demo.toLowerCase().normalize("NFD").replace(/[^a-z0-9]+/g, "-");
    await shot(`real-${slug}-limpio`);
    for (const label of ["Piezas", "3D"]) {
      const button = p.locator(`[data-testid=view-switch] button:has-text('${label}')`);
      if (await button.isDisabled()) continue;
      await button.click(); await p.waitForTimeout(1200); await shot(`real-${slug}-${label.toLowerCase()}`);
    }
    await p.goto(base);
    await p.waitForSelector("[data-testid=boot]", { state: "detached", timeout: 15000 });
  });
}
// Subida como «Mueble general» (vía general, geometry_only). Sin clave llega con el pendiente del modo con modelo.
if (general) {
  const gname = general.split(/[\\/]/).pop();
  await step("subir mueble general", async () => {
    await p.locator("button[aria-label='Modo de análisis']").click();
    await p.locator("[role=menuitem]:has-text('Mueble general')").click();
    await p.setInputFiles("#dxf-files", general);
    await p.waitForFunction((n) => [...document.querySelectorAll("[data-plan]")].some((el) => el.textContent.includes(n) && el.getAttribute("data-status") !== "analyzing"), gname, { timeout: 120000 });
    const status = await p.locator(`[data-plan]:has-text('${gname}')`).first().getAttribute("data-status");
    console.log(`     estado tras la subida: ${status}`);
  });
  await step("abrir mueble general", async () => {
    await p.locator(`[data-plan] button[aria-label^='${gname}']`).first().click();
    await p.waitForSelector("[data-testid=workbench]", { timeout: 30000 });
    await p.waitForTimeout(900);
    const text = await p.locator("[data-testid=pendientes-visibles]").innerText().catch(() => "");
    console.log(`     pendiente visible: ${text.replace(/\s+/g, " ").slice(0, 140)}`);
    await shot("real-general-subido");
    await p.locator("button[aria-label='Modo de análisis']").count();
    await p.goto(base);
    await p.waitForSelector("[data-testid=boot]", { state: "detached", timeout: 15000 });
    await p.locator("button[aria-label='Modo de análisis']").click();
    await p.locator("[role=menuitem]:has-text('Solo medidas')").click();
  });
}
const name = dxf.split(/[\\/]/).pop();
await step("subir", async () => {
  await p.setInputFiles("#dxf-files", dxf);
  await p.waitForFunction((n) => [...document.querySelectorAll("[data-plan]")].some((el) => el.textContent.includes(n) && el.getAttribute("data-status") !== "analyzing"), name, { timeout: 60000 });
});
await step("abrir mesa", async () => {
  await p.locator(`[data-plan] button[aria-label^='${name}']`).first().click();
  await p.waitForSelector("[data-testid=workbench]", { timeout: 30000 });
  await p.waitForTimeout(800);
  await shot("real-mesa");
});
for (const label of ["Original", "Piezas", "3D", "Limpio"]) {
  await step(`vista ${label}`, async () => { await p.locator(`[data-testid=view-switch] button:has-text('${label}')`).click(); await p.waitForTimeout(900); await shot(`real-${label.toLowerCase()}`); });
}
await step("seleccionar pieza", async () => { await p.locator("[data-row]").first().click(); await p.waitForSelector("[data-testid=ficha]"); await p.waitForTimeout(600); await shot("real-ficha"); });
for (const [step_, label] of [["Coste", "Coste"], ["Presupuesto", "Presupuesto"]]) {
  await step(`paso ${step_}`, async () => { await p.locator(`[data-testid=steps] button:has-text('${step_}')`).click(); await p.waitForSelector("[role=dialog]"); await p.waitForTimeout(900); await shot(`real-${label.toLowerCase()}`); await p.keyboard.press("Escape"); await p.waitForTimeout(300); });
}
await step("panel Revisión", async () => { await p.locator("[data-testid=action-blocks] button[aria-label='Revisión']").click(); await p.locator("[role=menuitem]:has-text('Revisar montaje')").click(); await p.waitForSelector("[role=dialog]"); await p.waitForTimeout(900); await shot("real-revision"); await p.keyboard.press("Escape"); });
await step("panel Similares", async () => { await p.locator("[data-testid=action-blocks] button[aria-label='Más']").click(); await p.locator("[role=menuitem]:has-text('Similares')").click(); await p.waitForSelector("[role=dialog]"); await p.waitForTimeout(1200); await shot("real-similares"); await p.keyboard.press("Escape"); });

console.log(`\nLlamadas /api: ${calls.length}`);
console.log(calls.join("\n"));
console.log(problems.length ? `\nProblemas:\n${problems.join("\n")}` : "\nSin errores de consola ni respuestas /api >= 400");
await browser.close();