// Capturas de plank-030 en la mesa de trabajo: carpeta, Original, Limpio, Piezas, 3D montado y por tipos, ficha y Traza.
// Uso: node scripts/portal-plank.mjs http://127.0.0.1:5175/ capturas/portal/plank [filtro]
import { chromium } from "playwright-core";
import fs from "node:fs";

const [, , base = "http://127.0.0.1:5175/", out = "capturas/portal/plank", filter = ""] = process.argv;
fs.mkdirSync(out, { recursive: true });
const wide = (p) => p.viewportSize().width >= 1024;

const ready = async (p) => {
  await p.waitForSelector("[data-testid=boot]", { state: "detached", timeout: 20000 });
  await p.waitForFunction(() => document.body.textContent.includes("Muebles procesados"), null, { timeout: 30000 });
};
const openFolder = async (p) => {
  await p.locator(wide(p) ? "aside button:has-text('Muebles procesados')" : "[role=listitem]:has-text('Muebles procesados')").first().click();
  await p.waitForFunction(() => [...document.querySelectorAll("[data-plan]")].some((el) => el.textContent.includes("Armario")), null, { timeout: 30000 });
  await p.waitForTimeout(400);
};
const openCase = async (p, title = "Armario plank-030") => {
  await openFolder(p);
  await p.locator(`[data-plan] button[aria-label^='${title}']`).first().click();
  await p.waitForSelector("[data-testid=workbench]", { timeout: 30000 });
  await p.waitForTimeout(600);
};
const view = async (p, label) => { await p.locator(`[data-testid=view-switch] button:has-text('${label}')`).click(); await p.waitForTimeout(800); };
const pick = async (p, id) => {
  if (!wide(p)) await p.locator("[data-testid=workbench] button[aria-expanded]").last().click();
  await p.locator(`[data-row='${id}']`).first().click();
  await p.waitForTimeout(400);
};
const more = async (p, label) => {
  if (wide(p)) {
    await p.locator("[data-testid=action-blocks] button:has-text('Más')").click();
  } else {
    await p.locator("button[aria-label='Acciones']").first().click();
  }
  await p.locator(`[role=menuitem]:has-text('${label}')`).first().click();
  await p.waitForTimeout(500);
};

const shots = [
  { name: "p0-carpeta", act: openFolder },
  { name: "p1-original", act: async (p) => { await openCase(p); await view(p, "Original"); } },
  { name: "p2-limpio", act: async (p) => { await openCase(p); await pick(p, "sides"); await view(p, "Limpio"); } },
  { name: "p3-piezas", act: async (p) => { await openCase(p); await view(p, "Piezas"); } },
  { name: "p4-3d-montaje", act: async (p) => { await openCase(p); await view(p, "3D"); }, delay: 1200 },
  { name: "p6-ficha", act: async (p) => { await openCase(p); await view(p, "3D"); await pick(p, "sides"); }, delay: 1200 },
  { name: "p7-traza", act: async (p) => { await openCase(p); await more(p, "Traza"); } },
  { name: "p2b-limpio-sin-seleccion", act: async (p) => { await openCase(p); await view(p, "Limpio"); } },
  { name: "p13-cajonera-limpio", act: async (p) => { await openCase(p, "Cajonera"); await view(p, "Limpio"); } },
  { name: "p14-piezas-separadas-3d", act: async (p) => { await openCase(p, "Piezas separadas, revisión 2"); await view(p, "3D"); }, delay: 1500 },
  { name: "p15-pdf-raster", act: async (p) => {
    await openFolder(p);
    await (wide(p) ? p.locator("aside button:has-text('Sin montaje')").first() : p.getByText("Sin montaje", { exact: true }).last()).click();
    await p.waitForTimeout(500);
    await p.locator("[data-plan] button[aria-label^='Tornillo de banco']").first().click();
    await p.waitForSelector("[data-testid=workbench]", { timeout: 30000 });
    await view(p, "Original");
  }, delay: 800 },
  { name: "p16-raro", act: async (p) => {
    await openFolder(p);
    await (wide(p) ? p.locator("aside button:has-text('Sin procesar')").first() : p.getByText("Sin procesar", { exact: true }).last()).click();
    await p.waitForTimeout(500);
    await p.locator("[data-plan] button[aria-label^='PlankAssembly 01']").first().click();
    await p.waitForSelector("[data-testid=workbench]", { timeout: 30000 });
    await view(p, "Limpio");
  }, delay: 800 },
  { name: "p17-recon-pieza", act: async (p) => { await openCase(p, "Mesa con bastidor (estudio)"); await view(p, "3D"); await pick(p, "faldon_frontal"); }, delay: 1800 },
  { name: "p18-plank016-limpio", act: async (p) => {
    await openFolder(p);
    await (wide(p) ? p.locator("aside button:has-text('Sin montaje')").first() : p.getByText("Sin montaje", { exact: true }).last()).click();
    await p.waitForTimeout(500);
    await p.locator("[data-plan] button[aria-label^='Mueble plank-016']").first().click();
    await p.waitForSelector("[data-testid=workbench]", { timeout: 30000 });
    await view(p, "Limpio");
  }, delay: 800 },
  { name: "p9-recon-3d", act: async (p) => { await openCase(p, "Mesa de trabajo"); await view(p, "3D"); }, delay: 1800 },
  { name: "p10-recon-v1", act: async (p) => { await openCase(p, "Mesa de trabajo"); await view(p, "3D"); await p.locator("[data-testid=version-1]").click(); }, delay: 1800 },
  { name: "p11-recon-original", act: async (p) => { await openCase(p, "Mesa de trabajo"); await view(p, "Original"); }, delay: 800 },
  { name: "p12-abstencion", act: async (p) => { await openCase(p, "Mesa sin escala"); await view(p, "3D"); await p.locator("[data-testid=version-1]").click(); }, delay: 800 },
  { name: "p8-mesa-3d", act: async (p) => { await openCase(p, "Mesa con revisión y coste"); await view(p, "3D"); }, delay: 1200 },
];

const browser = await chromium.launch({ executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe", headless: true, args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
for (const shot of shots.filter((item) => item.name.includes(filter))) {
  for (const width of [1440, 390]) {
    const ctx = await browser.newContext({ viewport: { width, height: width === 390 ? 844 : 900 } });
    const p = await ctx.newPage();
    const errors = [];
    p.on("pageerror", (error) => errors.push(error.message));
    p.on("console", (msg) => { if (msg.type() === "error") errors.push(msg.text()); });
    try {
      await p.goto(base);
      await ready(p);
      await shot.act(p);
      await p.waitForTimeout(shot.delay ?? 300);
      for (const close of await p.locator("[aria-label='Cerrar aviso']").all()) await close.click().catch(() => {});
      await p.mouse.move(1, 1);
      const file = `${out}/${shot.name}-${width}.png`;
      await p.screenshot({ path: file });
      const overflow = await p.evaluate(() => document.documentElement.scrollWidth - innerWidth);
      console.log(`${file}${overflow > 0 ? `  SCROLL HORIZONTAL ${overflow}px` : ""}${errors.length ? `  ERRORES ${errors.join(" | ")}` : ""}`);
    } catch (error) {
      console.log(`${shot.name}-${width} FALLO ${error.message.split("\n")[0]}`);
    }
    await ctx.close();
  }
}
await browser.close();
