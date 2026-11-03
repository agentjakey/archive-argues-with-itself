// Screenshots of the site's main screens, for before/after comparisons of a design change.
//   node scripts/ux-shots.mjs <base url> <out dir> [light|dark|both]
// Desktop 1440x900 and phone 390x844, the first screen of each page plus the full home page.
import { mkdirSync } from "node:fs";
import { chromium } from "@playwright/test";

const base = (process.argv[2] || "https://archiveargues.org").replace(/\/+$/, "");
const out = process.argv[3] || "shots";
const themes = (process.argv[4] || "dark") === "both" ? ["dark", "light"] : [process.argv[4] || "dark"];
mkdirSync(out, { recursive: true });

const seed = "How did federal health authorities describe tuberculosis control programs?";
const PAGES = [
  ["home", "/"],
  ["answer", `/?q=${encodeURIComponent(seed)}&jurisdiction=federal`],
  ["explore", "/?view=explore"],
  ["how", "/?view=how"],
  ["catalogue", "/catalogue/"],
  ["exhibit", "/exhibit/"],
  ["kiosk", "/exhibit/?kiosk=1"],
];
const SIZES = [
  ["desktop", { width: 1440, height: 900 }],
  ["phone", { width: 390, height: 844 }],
];

const browser = await chromium.launch();
for (const theme of themes) {
  for (const [size, viewport] of SIZES) {
    const context = await browser.newContext({ viewport, colorScheme: theme, reducedMotion: "reduce" });
    const page = await context.newPage();
    for (const [name, path] of PAGES) {
      const t0 = Date.now();
      await page.goto(base + path, { waitUntil: "networkidle", timeout: 60000 }).catch(() => undefined);
      await page.waitForTimeout(800);
      const file = `${out}/${name}-${size}-${theme}.png`;
      await page.screenshot({ path: file });
      if (name === "home") await page.screenshot({ path: `${out}/${name}-${size}-${theme}-full.png`, fullPage: true });
      console.log(file, `${Date.now() - t0} ms`);
    }
    await context.close();
  }
}
await browser.close();
