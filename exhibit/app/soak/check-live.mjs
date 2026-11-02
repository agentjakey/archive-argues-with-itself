// A live check of a published page: every request host, console errors, cookies and storage after
// the visit, and axe (WCAG 2.1 A and AA). Prints one JSON line.
//   node soak/check-live.mjs https://archiveargues.org/catalogue/
import { chromium } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const url = process.argv[2];
const browser = await chromium.launch();
const context = await browser.newContext();
const page = await context.newPage();
const hosts = new Set();
const errors = [];
page.on("request", (r) => hosts.add(new URL(r.url()).host));
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text().slice(0, 200)); });
page.on("pageerror", (e) => errors.push(String(e).slice(0, 200)));
await page.goto(url, { waitUntil: "networkidle" });
const clickable = page.locator("button, a[href^='#'], [role='tab']").first();
if (await clickable.count()) await clickable.click().catch(() => undefined);
await page.waitForTimeout(1500);
const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
const storage = await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length }));
const cookies = await context.cookies();
console.log(JSON.stringify({ url, hosts: [...hosts].sort(), errors, cookies: cookies.length, storage,
  axe_violations: axe.violations.map((v) => `${v.id} (${v.nodes.length})`) }));
await browser.close();
