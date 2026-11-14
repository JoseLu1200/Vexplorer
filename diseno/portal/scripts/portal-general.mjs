// Capturas de la vía de muebles generales en la mesa de trabajo (caso F02 y carpeta «Muebles procesados»).
// Uso: node scripts/portal-general.mjs http://127.0.0.1:5175/ capturas/portal/general [filtro]
import { chromium } from "playwright-core";
import fs from "node:fs";

const [, , base = "http://127.0.0.1:5175/", out = "capturas/portal/general", filter = ""] = process.argv;
fs.mkdirSync(out, { recursive: true });
const wide = (p) => p.viewportSize().width >= 1024;

const ready = async (p) => {
  await p.waitForSelector("[data-testid=boot]", { state: "detached", timeout: 15000 });
  await p.waitForFunction(() => [...document.querySelectorAll("[data-plan]")].some((el) => el.textContent.includes("Cajonera")), null, { timeout: 30000 });
};
const openFolder = async (p) => {
  await p.locator(wide(p) ? "aside button:has-text('Muebles procesados')" : "[role=listitem]:has-text('Muebles procesados')").first().click();
  await p.waitForTimeout(300);
};
const openCase = async (p, title = "Cajonera") => {
  await p.locator(`[data-plan] button[aria-label^='${title}']`).first().click();
  await p.waitForSelector("[data-testid=workbench]", { timeout: 20000 });
  await p.waitForTimeout(500);
};
const view = async (p, label) => { await p.locator(`[data-testid=view-switch] button:has-text('${label}')`).click(); await p.waitForTimeout(700); };
const pick = async (p, id) => {
  if (!wide(p)) await p.locator("[data-testid=workbench] button[aria-expanded]").last().click();
  await p.locator(`[data-row='${id}']`).click();
  await p.waitForTimeout(400);
};

const shots = [
  { name: "g0-carpeta", act: openFolder },
  { name: "g1-f02-original", act: async (p) => { await openCase(p); await pick(p, "frentes"); await view(p, "Original"); } },
  { name: "g2-f02-limpio", act: async (p) => { await openCase(p); await pick(p, "frentes"); await view(p, "Limpio"); } },
  { name: "g3-f02-piezas", act: async (p) => { await openCase(p); await pick(p, "frentes"); await view(p, "Piezas"); } },
  { name: "g4-f02-3d", act: async (p) => { await openCase(p); await pick(p, "frentes"); await view(p, "3D"); }, delay: 900 },
  { name: "g5-f02-inferida", act: async (p) => { await openCase(p); await pick(p, "trasera"); } },
  { name: "g6-f02-laminas", wideOnly: true, act: async (p) => { await openCase(p); await pick(p, "frentes"); await p.locator("[data-testid=ficha] button:has-text('Ver lámina')").click(); await p.waitForTimeout(500); } },
  { name: "g6b-f02-laminas-impresion", wideOnly: true, fullPage: true, act: async (p) => { await openCase(p); await pick(p, "frentes"); await p.locator("[data-testid=ficha] button:has-text('Ver lámina')").click(); await p.waitForTimeout(400); await p.emulateMedia({ media: "print" }); await p.waitForTimeout(300); } },
  { name: "g7-f02-pendientes", act: async (p) => { await openCase(p); await p.locator("[data-testid=ind-pendientes]").click(); await p.waitForTimeout(400); } },
  { name: "g8-f01-3d", act: async (p) => { await openCase(p, "Mesa"); await view(p, "3D"); }, delay: 900 },
  { name: "g9-estanteria-legacy-3d", act: async (p) => { await openCase(p, "Estantería de 900"); await pick(p, "piece-proposal-between-sides-side_panel"); await view(p, "3D"); }, delay: 900 },
];

const browser = await chromium.launch({ executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe", headless: true });
for (const shot of shots.filter((item) => item.name.includes(filter))) {
  for (const width of [1440, 390]) {
    if (shot.wideOnly && width < 1024) continue;
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
