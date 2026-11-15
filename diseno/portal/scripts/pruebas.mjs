// Pruebas de comportamiento contra el build de un solo archivo (modo de ejemplo), con el Chrome instalado.
// Uso: node scripts/pruebas.mjs http://localhost:4417/
// Comprueba: arrastre de varios DXF y un PDF a la ventana y a una carpeta, medición, descarga del DXF original
// (sha256 contra el archivo de origen), persistencia tras recargar, fallo de IndexedDB, movimiento reducido,
// enlace por hover entre plano y despiece, capas y revisión desde el despiece.
import { chromium } from "playwright-core";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

const base = process.argv[2] ?? "http://localhost:4417/";
const DXF_DIR = "src/assets/dxf";
const sha = (buffer) => crypto.createHash("sha256").update(buffer).digest("hex");
const results = [];
const check = (name, ok, detail = "") => { results.push({ name, ok, detail }); console.log(`${ok ? "OK   " : "FALLA"} ${name}${detail ? ` · ${detail}` : ""}`); };

const browser = await chromium.launch({ executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe", headless: true, args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });

async function newPage(context) {
  const page = await context.newPage();
  page.errors = [];
  page.on("pageerror", (e) => page.errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error") page.errors.push(m.text()); });
  return page;
}
async function ready(page) {
  await page.waitForSelector("[data-testid=boot]", { state: "detached", timeout: 15000 });
  await page.waitForFunction(() => document.querySelectorAll("[data-plan]").length >= 6 && !document.querySelector("[data-plan][data-status=analyzing]"), null, { timeout: 20000 });
}
async function drop(page, selector, files) {
  const payload = files.map((f) => ({ name: f.name, type: f.type, b64: f.buffer.toString("base64") }));
  const dt = await page.evaluateHandle((list) => {
    const transfer = new DataTransfer();
    for (const f of list) transfer.items.add(new File([Uint8Array.from(atob(f.b64), (c) => c.charCodeAt(0))], f.name, { type: f.type }));
    return transfer;
  }, payload);
  await page.dispatchEvent(selector, "dragenter", { dataTransfer: dt });
  await page.dispatchEvent(selector, "dragover", { dataTransfer: dt });
  const overlay = await page.locator("[data-testid=drop-overlay]").textContent().catch(() => "");
  await page.dispatchEvent(selector, "drop", { dataTransfer: dt });
  return overlay;
}
async function openPlan(page, name) {
  await page.locator(`[data-plan] button[aria-label^='${name}']`).first().click();
  await page.waitForSelector("[aria-label='Clases de dato'] >> visible=true", { timeout: 20000 });
}

const completo = fs.readFileSync(path.join(DXF_DIR, "piezas_completo.dxf"));
const qty = fs.readFileSync(path.join(DXF_DIR, "piezas_qty_desconocida.dxf"));
const principal = fs.readFileSync(path.join(DXF_DIR, "piezas_espesor_desconocido.dxf"));

// ---- 1. Arrastre de varios archivos a la ventana y a una carpeta, descarga y persistencia ----
{
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true });
  const page = await newPage(context);
  await page.goto(base);
  await ready(page);
  check("siembra: seis planos en tres carpetas", (await page.locator("[data-plan]").count()) === 6 && (await page.locator("aside [data-drop-folder]").count()) === 4);

  const overlay = await drop(page, "main", [
    { name: "estanteria_cliente_a.dxf", type: "application/dxf", buffer: completo },
    { name: "estanteria_cliente_b.dxf", type: "application/dxf", buffer: qty },
    { name: "plano-conjunto.pdf", type: "application/pdf", buffer: Buffer.from("%PDF-1.4\n%") },
  ]);
  check("arrastre: aviso de destino sobre la ventana", /Suelta para añadir a/.test(overlay ?? ""), overlay?.trim());
  await page.waitForSelector("[data-testid=queue]", { timeout: 5000 });
  check("arrastre: tres filas en la cola", (await page.locator("[data-testid=queue-item]").count()) === 3);
  await page.waitForFunction(() => [...document.querySelectorAll("[data-testid=queue-item]")].every((el) => ["done", "error"].includes(el.getAttribute("data-stage"))), null, { timeout: 30000 });
  const stages = await page.locator("[data-testid=queue-item]").evaluateAll((els) => els.map((el) => `${el.querySelector(".font-mono")?.textContent}:${el.getAttribute("data-stage")}`));
  check("arrastre: los dos DXF terminan y el PDF falla", stages.filter((s) => s.endsWith(":done")).length === 2 && stages.some((s) => s.startsWith("plano-conjunto.pdf:error")), stages.join(", "));
  const queueError = await page.locator("[data-testid=queue-error]").first().textContent();
  check("arrastre: error por archivo", /Formato no admitido/.test(queueError ?? ""), queueError ?? "");

  // A una carpeta concreta de la barra lateral
  const folder = page.locator("aside [data-drop-folder]", { hasText: "Serie E-1000" }).first();
  const folderId = await folder.getAttribute("data-drop-folder");
  const overlay2 = await drop(page, `aside [data-drop-folder="${folderId}"]`, [{ name: "variante_carpeta.dxf", type: "application/dxf", buffer: principal }]);
  check("arrastre a carpeta: el aviso nombra la carpeta", /Serie E-1000/.test(overlay2 ?? ""), overlay2?.trim());
  await page.waitForFunction(() => [...document.querySelectorAll("[data-testid=queue-item]")].length === 4 && [...document.querySelectorAll("[data-testid=queue-item]")].every((el) => ["done", "error"].includes(el.getAttribute("data-stage"))), null, { timeout: 30000 });
  await folder.locator("button").first().click();
  await page.waitForTimeout(300);
  const inFolder = await page.locator("[data-plan] button[aria-label^='variante_carpeta.dxf']").count();
  check("arrastre a carpeta: el plano queda en Serie E-1000", inFolder === 1);

  // Descarga del DXF original de un ejemplo
  await page.locator("aside button", { hasText: "Todos los planos" }).click();
  await openPlan(page, "piezas_completo.dxf").catch(() => {});
  await page.waitForSelector("[data-testid=open-cad]", { timeout: 10000 });
  const [download] = await Promise.all([page.waitForEvent("download", { timeout: 10000 }), page.locator("[data-testid=open-cad] >> visible=true").first().click()]);
  const saved = await download.path();
  const got = sha(fs.readFileSync(saved));
  check("Abrir en CAD: descarga el DXF de ejemplo idéntico al original", got === sha(completo) && download.suggestedFilename() === "piezas_completo.dxf", `${download.suggestedFilename()} ${got.slice(0, 12)}`);

  // Persistencia: recargar y descargar el archivo arrastrado desde IndexedDB
  await page.goto(base + "#/");
  await page.reload();
  await page.waitForSelector("[data-testid=boot]", { state: "detached", timeout: 15000 });
  await page.waitForFunction(() => document.querySelectorAll("[data-plan]").length >= 9, null, { timeout: 15000 });
  const count = await page.locator("[data-plan]").count();
  check("recarga: los planos arrastrados siguen en el espacio de trabajo", count === 10, `${count} planos`);
  await page.waitForFunction(() => !document.querySelector("[data-plan][data-status=analyzing]"), null, { timeout: 30000 });
  // Tras recargar, el mock ya no tiene el análisis: el plano tiene que terminar de abrirse con el DXF guardado.
  await openPlan(page, "estanteria_cliente_a.dxf");
  check("recarga: un plano arrastrado se vuelve a abrir con su despiece", (await page.locator("tr[data-row]").count()) > 0);
  const [download2] = await Promise.all([page.waitForEvent("download", { timeout: 10000 }), page.locator("[data-testid=open-cad] >> visible=true").first().click()]);
  const got2 = sha(fs.readFileSync(await download2.path()));
  check("recarga: Abrir en CAD devuelve el archivo arrastrado guardado en IndexedDB", got2 === sha(completo) && download2.suggestedFilename() === "estanteria_cliente_a.dxf", `${download2.suggestedFilename()} ${got2.slice(0, 12)}`);
  check("sin errores de consola (arrastre y descarga)", page.errors.length === 0, page.errors.slice(0, 3).join(" | "));
  await context.close();
}

// ---- 2. Medición, capas, enlace por hover y revisión desde el despiece ----
{
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await newPage(context);
  await page.goto(base);
  await ready(page);
  await openPlan(page, "piezas_espesor_desconocido.dxf");
  await page.waitForTimeout(400);

  // Enlace: hover sobre la fila de K1 marca sus contornos; hover sobre un contorno marca su fila
  await page.locator("tr[data-row]").first().hover();
  const strokeHover = await page.locator("[data-contour='contour-entity-8D']").getAttribute("stroke");
  check("hover en fila: el contorno de la pieza se marca", strokeHover === "rgb(var(--select))", strokeHover ?? "");
  const box = await page.locator("[data-contour='contour-entity-F4']").boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.waitForTimeout(150);
  const rowClass = await page.locator("tr[data-row]").last().getAttribute("class");
  check("hover en contorno: su fila se marca en el despiece", /bg-sunken/.test(rowClass ?? ""));

  // Medición entre dos vértices del contorno de K1 (alzado, 1200 × 300)
  await page.locator("button:has-text('Medir')").click();
  const k1 = await page.locator("[data-contour='contour-entity-8D']").boundingBox();
  await page.mouse.click(k1.x + 1, k1.y + k1.height - 1);
  await page.mouse.click(k1.x + k1.width - 1, k1.y + k1.height - 1);
  const k1After = await page.locator("[data-contour='contour-entity-8D']").boundingBox();
  // La medida queda fija al mover el puntero y el lienzo no se ha desplazado entre los dos clics.
  await page.mouse.move(k1.x + k1.width / 2, k1.y - 120);
  const value = (await page.locator("[data-testid=measure-value]").textContent())?.replace(/\s+/g, " ").trim();
  check("medir: dos vértices de K1 dan 1200 mm y la medida queda fija", value === "1200 mm" && Math.abs(k1After.x - k1.x) < 1, `${value ?? ""} · desplazamiento ${Math.round(k1After.x - k1.x)} px`);
  await page.keyboard.press("Escape");
  await page.keyboard.press("Escape");

  // Capas: apagar cotas quita sus rótulos
  const dimsBefore = await page.locator("svg text", { hasText: /^864$/ }).count();
  await page.locator("button:has-text('Capas')").click();
  await page.locator("label:has-text('Cotas') input").uncheck();
  const dimsAfter = await page.locator("svg text", { hasText: /^864$/ }).count();
  check("capas: apagar Cotas quita los rótulos de cota", dimsBefore > 0 && dimsAfter === 0, `${dimsBefore} → ${dimsAfter}`);
  await page.locator("label:has-text('Cotas') input").check();
  await page.keyboard.press("Escape");

  // Completar el grosor desconocido de K3 desde el despiece
  await page.locator("tr[data-row] button:has-text('desconocido')").first().click();
  await page.fill("#inline-thickness", "18");
  await page.fill("#inline-reason", "Grosor confirmado con compras");
  await page.fill("#inline-reviewer", "L. Ferrer");
  await page.locator("button:has-text('Crear revisión 2') >> visible=true").click();
  await page.waitForSelector("text=Revisión 2 guardada", { timeout: 8000 });
  const tag = await page.locator("header").textContent();
  check("completar desde el despiece: crea la revisión 2 y avisa", /r2/.test(tag ?? "") && /Completo/.test(tag ?? ""));

  // Arrastrar dos DXF con el plano abierto: el mock les da el mismo run_id y el plano abierto no debe perder la pieza elegida
  // K3 ya queda elegida al completarla; un clic más la soltaría.
  if (!/K3/.test((await page.locator("tr[aria-selected=true]").first().textContent().catch(() => "")) ?? "")) await page.locator("tr[data-row]", { hasText: "K3" }).first().click();
  await drop(page, "main", [
    { name: "otra_a.dxf", type: "application/dxf", buffer: principal },
    { name: "otra_b.dxf", type: "application/dxf", buffer: principal },
  ]);
  await page.waitForFunction(() => [...document.querySelectorAll("[data-testid=queue-item]")].length === 2 && [...document.querySelectorAll("[data-testid=queue-item]")].every((el) => ["done", "error"].includes(el.getAttribute("data-stage"))), null, { timeout: 30000 });
  await page.waitForTimeout(4000);
  const skeleton = await page.locator("[data-testid=plan-skeleton]").count();
  const selectedRow = await page.locator("tr[aria-selected=true]").first().textContent().catch(() => "");
  const header2 = await page.locator("header").textContent();
  check("arrastre con el plano abierto: sin esqueleto, con K3 elegida y la revisión 2", skeleton === 0 && /K3/.test(selectedRow ?? "") && /r2/.test(header2 ?? ""), `${skeleton} esqueletos · fila ${selectedRow?.slice(0, 12)}`);

  // Recargar con la revisión 2 hecha: el plano se rehace en el mock y repite la revisión guardada
  await page.reload();
  await page.waitForSelector("[data-testid=boot]", { state: "detached", timeout: 15000 });
  await page.waitForSelector("[aria-label='Clases de dato'] >> visible=true", { timeout: 20000 });
  const header3 = await page.locator("header").textContent();
  check("recarga con revisión: el plano vuelve con la revisión 2 repetida", /r2/.test(header3 ?? "") && /Completo/.test(header3 ?? ""));

  // Plano de ejemplo sin revisión grabada: el 422 del mock se enseña, no se oculta
  await page.goto(base + "#/");
  await page.waitForTimeout(400);
  await openPlan(page, "piezas_qty_desconocida.dxf");
  await page.locator("tr[data-row] button:has-text('desconocido')").first().click();
  await page.fill("#inline-quantity", "4");
  await page.fill("#inline-reason", "Cantidad confirmada con taller");
  await page.fill("#inline-reviewer", "L. Ferrer");
  await page.locator("button:has-text('Crear revisión 2') >> visible=true").click();
  const alert = await page.locator("form [role=alert] >> visible=true").first().textContent({ timeout: 8000 }).catch(() => "");
  check("completar en un plano sin revisión grabada: enseña el error del servidor", /revisión grabada/.test(alert ?? ""), alert?.slice(0, 80));
  check("sin errores de consola (plano)", page.errors.length === 0, page.errors.slice(0, 3).join(" | "));
  await context.close();
}

// ---- 3. IndexedDB rota: la app funciona en memoria ----
{
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await context.addInitScript(() => {
    Object.defineProperty(window, "indexedDB", { configurable: true, get() { return { open() { throw new Error("bloqueado"); } }; } });
  });
  const page = await newPage(context);
  await page.goto(base);
  await ready(page);
  const warning = await page.locator("text=no guarda los planos").count();
  check("sin IndexedDB: lista los planos y avisa de que no se guardan", (await page.locator("[data-plan]").count()) === 6 && warning === 1);
  await openPlan(page, "piezas_espesor_desconocido.dxf");
  check("sin IndexedDB: abre un plano", (await page.locator("tr[data-row]").count()) > 0);
  check("sin errores de consola (sin IndexedDB)", page.errors.length === 0, page.errors.slice(0, 3).join(" | "));
  await context.close();
}

// ---- 4. Movimiento reducido ----
{
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
  const page = await newPage(context);
  const t0 = Date.now();
  await page.goto(base);
  await page.waitForSelector("[data-testid=boot]", { state: "detached", timeout: 15000 });
  check("movimiento reducido: el arranque no se alarga", Date.now() - t0 < 4000, `${Date.now() - t0} ms`);
  await ready(page);
  await openPlan(page, "piezas_espesor_desconocido.dxf");
  await page.locator("nav[aria-label='Pantallas del plano'] a:has-text('Análisis') >> visible=true").click();
  await page.waitForSelector("path.draw-in", { timeout: 8000 });
  const anim = await page.locator("path.draw-in").first().evaluate((el) => getComputedStyle(el).animationName);
  check("movimiento reducido: el plano de análisis aparece sin animación", anim === "none", anim);
  await context.close();
}

await browser.close();
const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length} de ${results.length} comprobaciones correctas`);
process.exit(failed.length ? 1 : 0);
