// Capturas de «Ver el proceso».
//   guiado:  plank-030 guardado, cada paso a 1440 y 390 (modo de ejemplo).
//   subida:  mesa_demo_001.dxf como «Mesa» y plank-030.dxf como «Mueble general» contra el backend real.
// Uso: node scripts/portal-proceso.mjs guiado http://127.0.0.1:5175/ capturas/portal/proceso
//      node scripts/portal-proceso.mjs subida http://127.0.0.1:5177/ capturas/portal/proceso <ruta-vexplorer>
import { chromium } from "playwright-core";
import fs from "node:fs";
import path from "node:path";

const [, , modo = "guiado", base = "http://127.0.0.1:5175/", out = "capturas/portal/proceso", vexplorer = "C:/Users/marti/Proyectos/Vexplorer"] = process.argv;
fs.mkdirSync(out, { recursive: true });
const wide = (p) => p.viewportSize().width >= 1024;
const browser = await chromium.launch({ executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe", headless: true, args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });

async function page(width) {
  const ctx = await browser.newContext({ viewport: { width, height: width === 390 ? 844 : 900 } });
  const p = await ctx.newPage();
  const errors = [];
  p.on("pageerror", (error) => errors.push(error.message));
  p.on("console", (msg) => { if (msg.type() === "error") errors.push(msg.text()); });
  p.on("response", (r) => { if (r.url().includes("/api/v1/") && r.status() >= 400) errors.push(`${r.status()} ${new URL(r.url()).pathname}`); });
  await p.goto(base);
  await p.waitForSelector("[data-testid=boot]", { state: "detached", timeout: 20000 });
  return { ctx, p, errors };
}
const shot = async (p, errors, name) => {
  for (const close of await p.locator("[aria-label='Cerrar aviso']").all()) await close.click().catch(() => {});
  await p.mouse.move(1, 1);
  const file = `${out}/${name}-${p.viewportSize().width}.png`;
  await p.screenshot({ path: file });
  const overflow = await p.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  console.log(`${file}${overflow > 0 ? `  SCROLL HORIZONTAL ${overflow}px` : ""}${errors.length ? `  ERRORES ${errors.splice(0).join(" | ")}` : ""}`);
};
const openFolder = async (p, name = "Muebles procesados") => {
  await p.waitForFunction((n) => document.body.textContent.includes(n), name, { timeout: 30000 });
  await p.locator(wide(p) ? `aside button:has-text('${name}')` : `[role=listitem]:has-text('${name}')`).first().click();
  await p.waitForTimeout(500);
};
const pasos = async (p) => (await p.locator("[data-testid=proceso] [data-paso]").evaluateAll((els) => els.map((el) => `${el.dataset.paso}:${el.dataset.estado}`))).join(" ");

if (modo === "destacados" || modo === "png") {
  for (const width of modo === "destacados" ? [1440, 390] : [1440]) {
    const { ctx, p, errors } = await page(width);
    try {
      await p.waitForSelector("[data-testid=destacados]", { timeout: 30000 });
      await p.waitForTimeout(600);
      if (modo === "destacados") {
        await shot(p, errors, "entrada-destacados");
        await p.locator("[data-destacado=recon_caso01]").click();
        await p.waitForSelector("[data-testid=proceso]", { timeout: 30000 });
        await p.waitForTimeout(1200);
        console.log(`destacado abre: ${await pasos(p)}`);
        await shot(p, errors, "entrada-destacado-abierto");
      } else {
        await p.setInputFiles("#dxf-files", path.join(vexplorer, "data/full_app_demo/reconstruction/00dbf06fac402177f21a35d2a2e31ecc/source.png"));
        await p.waitForSelector("[data-testid=proceso]", { timeout: 30000 });
        await p.waitForTimeout(1200);
        const titulo = await p.locator("[data-testid=workbench] h1").textContent();
        const tarjetas = await p.evaluate(() => location.hash);
        console.log(`png abre ${titulo} en ${tarjetas}: ${await pasos(p)}`);
        await shot(p, errors, "subida-png-estudio01");
      }
    } catch (error) { console.log(`${modo}-${width} FALLO ${error.message.split("\n")[0]} ${errors.join(" | ")}`); }
    await ctx.close();
  }
} else if (modo === "recon") {
  // «Ver el proceso» de un trabajo de Construcción 3D: un paso por captura. Título del caso en el 5.º argumento.
  const titulo = process.argv[6] ?? "Mesa con bastidor (estudio)";
  const prefijo = process.argv[7] ?? "estudio01";
  const { ctx, p, errors } = await page(1440);
  try {
    await openFolder(p);
    await p.locator(`[data-plan] button[aria-label^='${titulo}']`).first().click();
    await p.waitForSelector("[data-testid=workbench]", { timeout: 30000 });
    await p.locator("[data-testid=ver-proceso]").click();
    await p.waitForSelector("[data-testid=proceso]");
    const ids = await p.locator("[data-testid=proceso] [data-paso]").evaluateAll((els) => els.map((el) => el.dataset.paso));
    console.log(`pasos ${await pasos(p)}`);
    for (let i = 0; i < ids.length; i++) {
      if (i) await p.locator("[data-testid=proceso-siguiente]").click();
      await p.waitForTimeout(["montaje", "comprobaciones", "refinamiento"].includes(ids[i]) ? 2200 : 1200);
      await shot(p, errors, `${prefijo}-${String(i + 1).padStart(2, "0")}-${ids[i]}`);
    }
  } catch (error) { console.log(`recon FALLO ${error.message.split("\n")[0]} ${errors.join(" | ")}`); }
  await ctx.close();
} else if (modo === "huella") {
  // Subida con el tipo por defecto: la huella SHA-256 tiene que llevar al resultado guardado.
  for (const [nombre, archivo] of [
    ["plank030", "data/plank_pipeline_demo/runs/run-9eb5e3aca8a04331ac0b0d3e5e2f2f40/source.dxf"],
    ["plank016", "data/plank_pipeline_demo/runs/run-dbf758e4fbcd4b19bff8552201a48d4a/source.dxf"],
    ["F02", "data/cad_completion_controls/public/F02.dxf"],
  ]) {
    const { ctx, p, errors } = await page(1440);
    try {
      await p.waitForSelector("#dxf-files", { state: "attached", timeout: 20000 });
      await p.setInputFiles("#dxf-files", path.join(vexplorer, archivo));
      await p.waitForFunction(() => [...document.querySelectorAll("[data-plan]")].some((el) => /plank|Cajonera|Armario|Mueble/.test(el.textContent) && !el.textContent.includes("source.dxf") && el.querySelector("svg")), null, { timeout: 90000 }).catch(() => {});
      await p.waitForTimeout(1500);
      await p.waitForFunction(() => [...document.querySelectorAll("[data-plan]")].some((el) => el.textContent.includes("Sin carpeta") && !el.textContent.includes("source.dxf") && !el.textContent.includes(".dxf")), null, { timeout: 90000 }).catch(() => {});
      const tarjeta = await p.locator("[data-plan]", { hasText: "Sin carpeta" }).evaluateAll((els) => els.map((el) => el.textContent.replace(/\s+/g, " ").trim()));
      console.log(`${nombre}: tarjetas ${JSON.stringify(tarjeta)}`);
      await shot(p, errors, `huella-${nombre}-1-tarjeta`);
      const card = p.locator("[data-plan]", { hasText: "Sin carpeta" }).first().locator("button[aria-label]").first();
      await card.click();
      await p.waitForSelector("[data-testid=workbench]", { timeout: 60000 });
      await p.waitForSelector("[data-testid=proceso]", { timeout: 15000 }).catch(() => {});
      console.log(`${nombre}: pasos ${await pasos(p).catch(() => "sin proceso")}`);
      await p.waitForTimeout(1200);
      await shot(p, errors, `huella-${nombre}-2-proceso`);
    } catch (error) { console.log(`huella-${nombre} FALLO ${error.message.split("\n")[0]} ${errors.join(" | ")}`); }
    await ctx.close();
  }
} else if (modo === "guiado") {
  for (const width of [1440, 390]) {
    const { ctx, p, errors } = await page(width);
    try {
      await openFolder(p);
      await p.locator("[data-plan] button[aria-label^='Armario plank-030']").first().click();
      await p.waitForSelector("[data-testid=workbench]", { timeout: 30000 });
      await p.locator("[data-testid=ver-proceso]").click();
      await p.waitForSelector("[data-testid=proceso]");
      console.log(`pasos ${await pasos(p)}`);
      const ids = ["plano", "limpieza", "propuesta", "revision", "montaje", "salidas"];
      for (let i = 0; i < ids.length; i++) {
        if (i) await p.locator("[data-testid=proceso-siguiente]").click();
        await p.waitForTimeout(ids[i] === "montaje" ? 1500 : 800);
        await shot(p, errors, `${i + 1}-${ids[i]}`);
      }
    } catch (error) { console.log(`guiado-${width} FALLO ${error.message.split("\n")[0]}`); }
    await ctx.close();
  }
} else {
  const subir = async (p, tipo, archivo) => {
    await p.locator("button[aria-label='Modo de análisis'], button[aria-label='Modo']").first().click().catch(async () => {
      await p.locator("[aria-haspopup=menu]").filter({ has: p.locator("svg") }).first().click();
    });
    await p.locator(`[role=menuitem]:has-text('${tipo}')`).first().click();
    await p.setInputFiles("#dxf-files", archivo);
  };
  // a) Mesa con plantilla, en vivo
  {
    const { ctx, p, errors } = await page(1440);
    try {
      await subir(p, "Mesa", path.join(vexplorer, "data/planos_demo/mesa_demo_001.dxf"));
      await p.waitForSelector("[data-testid=proceso]", { timeout: 20000 });
      await p.waitForTimeout(300);
      await shot(p, errors, "subida-mesa-1-en-curso");
      await p.waitForSelector("[data-testid=workbench]", { timeout: 60000 });
      await p.waitForSelector("[data-testid=proceso]");
      await p.locator("[data-testid=proceso] [data-paso=revision]").click();
      await p.waitForTimeout(800);
      console.log(`pasos r1 ${await pasos(p)}`);
      await shot(p, errors, "subida-mesa-2-aceptar");
      await p.locator("[data-testid=accion-proceso]").click();
      await p.waitForFunction(() => document.querySelector("[data-paso=montaje]")?.getAttribute("data-estado") === "hecho", null, { timeout: 60000 }).catch(() => {});
      await p.locator("[data-testid=ver-proceso]").isVisible();
      if (!(await p.locator("[data-testid=proceso]").count())) await p.locator("[data-testid=ver-proceso]").click();
      await p.locator("[data-testid=proceso] [data-paso=montaje]").click();
      await p.waitForTimeout(1500);
      console.log(`pasos r2 ${await pasos(p)}`);
      await shot(p, errors, "subida-mesa-3-montaje");
      await p.locator("[data-testid=proceso] [data-paso=salidas]").click();
      await p.waitForTimeout(1200);
      await shot(p, errors, "subida-mesa-4-salidas");
    } catch (error) { console.log(`subida-mesa FALLO ${error.message.split("\n")[0]} ${errors.join(" | ")}`); }
    await ctx.close();
  }
  // c) plank-030 como mueble general: geometría en vivo y el resto guardado
  {
    const { ctx, p, errors } = await page(1440);
    try {
      await subir(p, "Mueble general", path.join(vexplorer, "data/plank_pipeline_demo/runs/run-9eb5e3aca8a04331ac0b0d3e5e2f2f40/source.dxf"));
      await p.waitForSelector("[data-testid=proceso]", { timeout: 20000 });
      await shot(p, errors, "subida-plank-1-en-curso");
      await p.waitForSelector("[data-testid=workbench]", { timeout: 60000 });
      await p.waitForSelector("[data-testid=proceso]");
      await p.waitForTimeout(500);
      console.log(`pasos plank ${await pasos(p)}`);
      await p.locator("[data-testid=proceso] [data-paso=montaje]").click();
      await p.waitForTimeout(1500);
      await shot(p, errors, "subida-plank-2-montaje");
    } catch (error) { console.log(`subida-plank FALLO ${error.message.split("\n")[0]} ${errors.join(" | ")}`); }
    await ctx.close();
  }
}
await browser.close();
