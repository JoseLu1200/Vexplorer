// Diagnóstico: anchos de los ancestros de la primera tabla a 390 px.
import { chromium } from "playwright-core";
const b = await chromium.launch({ executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe", headless: true });
const p = await b.newPage({ viewport: { width: 390, height: 844 } });
await p.goto(process.argv[2]);
await p.waitForSelector("table", { timeout: 20000 });
console.log(await p.evaluate(() => {
  const out = [];
  let q = document.querySelector("table");
  while (q) { out.push(`${q.tagName}.${String(q.className).slice(0, 70)} w=${Math.round(q.getBoundingClientRect().width)} ox=${getComputedStyle(q).overflowX}`); q = q.parentElement; }
  return out.join("\n");
}));
await b.close();
