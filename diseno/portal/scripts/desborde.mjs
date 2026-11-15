import { chromium } from "playwright-core";
const [, , url] = process.argv;
const b = await chromium.launch({ executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe", headless: true });
const p = await b.newPage({ viewport: { width: 390, height: 844 } });
await p.goto(url); await p.waitForTimeout(6000);
console.log(await p.evaluate(() => {
  const out = [];
  for (const el of document.querySelectorAll("body *")) {
    const r = el.getBoundingClientRect();
    if (r.right > innerWidth + 1) {
      let a = el.parentElement, clipped = false;
      while (a) { const s = getComputedStyle(a); if (s.overflowX !== "visible") { clipped = a.getBoundingClientRect().right <= innerWidth + 1; break; } a = a.parentElement; }
      if (!clipped) { const chain=[]; let q=el; for(let i=0;i<7&&q;i++){chain.push(q.tagName+"."+String(q.className?.baseVal ?? q.className).slice(0,50)); q=q.parentElement;} out.push(chain.join(" < ")+" right="+Math.round(r.right)); }
    }
  }
  return out.slice(0, 12).join("\n") + `\nscrollWidth=${document.documentElement.scrollWidth}`;
}));
await b.close();
