// Diagnóstico rápido: abre una URL, espera y guarda una captura con los errores de consola.
// Uso: node scripts/sonda.mjs <url> <salida.png> [ancho] [alto] [espera_ms]
import { chromium } from "playwright-core";
const [, , url, out = "sonda.png", w = "1440", h = "900", wait = "4000"] = process.argv;
const browser = await chromium.launch({ executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe", headless: true, args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
const page = await browser.newPage({ viewport: { width: Number(w), height: Number(h) } });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
page.on("console", (m) => { if (m.type() === "error" || m.type() === "warning") errors.push(`${m.type()}: ${m.text()}`); });
await page.goto(url);
await page.waitForTimeout(Number(wait));
await page.screenshot({ path: out, fullPage: true });
console.log(errors.length ? errors.join("\n") : "sin errores");
console.log("scrollWidth", await page.evaluate(() => document.documentElement.scrollWidth), "url", page.url());
await browser.close();
