// The kiosk soak test: hours of scripted visits against the kiosk server with every outside host
// blocked (as a library kiosk with no network), sampling memory once a minute.
//
//   node soak/soak.mjs --hours 8 --url http://127.0.0.1:8765/exhibit/ --out ../../reports/v2/exhibit/soak
//
// Each sample records the page's JS heap and DOM node count (Chrome DevTools Protocol) and the
// working set of the browser and all its child processes (Windows, from Win32_Process). The summary
// fits a straight line to the samples after the first hour, and reports the slope per hour with its
// standard error, every page crash and every uncaught page error. It passes when nothing crashed,
// nothing threw, and neither the heap nor the working set grew by more than the stated limits per
// hour. The limits are written into the summary with the result.
import { chromium } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { appendFileSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, a, i, all) => (a.startsWith("--") ? [...acc, [a.slice(2), all[i + 1]]] : acc), []),
);
const HOURS = Number(args.hours ?? 8);
const URL = args.url ?? "http://127.0.0.1:8765/exhibit/";
const OUT = args.out ?? "../../reports/v2/exhibit/soak";
const CHANNEL = args.channel ?? "msedge";        // the kiosk's browser
const SAMPLE_MS = 60_000;
const WARMUP_MS = 60 * 60_000;
const LIMITS = { heap_mb_per_hour: 1.0, working_set_mb_per_hour: 10.0 };

const stamp = new Date().toISOString().replace(/[:.]/g, "-");
mkdirSync(OUT, { recursive: true });
const samplesPath = join(OUT, `soak-${stamp}.jsonl`);
const summaryPath = join(OUT, `soak-${stamp}-summary.json`);

function processTreeBytes(rootPid) {
  if (process.platform !== "win32" || !rootPid) return null;
  const script =
    `$all = Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,WorkingSetSize; ` +
    `$ids = @(${rootPid}); $added = $true; ` +
    `while ($added) { $added = $false; foreach ($p in $all) { if ($ids -contains $p.ParentProcessId -and -not ($ids -contains $p.ProcessId)) { $ids += $p.ProcessId; $added = $true } } }; ` +
    `($all | Where-Object { $ids -contains $_.ProcessId } | Measure-Object WorkingSetSize -Sum).Sum`;
  try {
    return Number(execFileSync("powershell", ["-NoProfile", "-Command", script], { encoding: "utf8" }).trim());
  } catch {
    return null;
  }
}

function fit(points) {
  // Least squares y = a + b x, with the standard error of b.
  const n = points.length;
  if (n < 3) return null;
  const mx = points.reduce((s, p) => s + p[0], 0) / n;
  const my = points.reduce((s, p) => s + p[1], 0) / n;
  const sxx = points.reduce((s, p) => s + (p[0] - mx) ** 2, 0);
  const sxy = points.reduce((s, p) => s + (p[0] - mx) * (p[1] - my), 0);
  const b = sxy / sxx;
  const a = my - b * mx;
  const rss = points.reduce((s, p) => s + (p[1] - a - b * p[0]) ** 2, 0);
  const se = Math.sqrt(rss / (n - 2) / sxx);
  return { slope: b, se, n };
}

const server = await chromium.launchServer({ channel: CHANNEL, headless: false, args: ["--kiosk-printing"] });
const browser = await chromium.connect(server.wsEndpoint());
const browserPid = server.process().pid;
const context = await browser.newContext({ viewport: { width: 1920, height: 1080 }, hasTouch: true });
// No network but the kiosk itself: every request to another host fails, as on an offline kiosk.
await context.route((url) => url.hostname !== "127.0.0.1", (route) => route.abort("internetdisconnected"));
const page = await context.newPage();
const cdp = await context.newCDPSession(page);
await cdp.send("Performance.enable");

const events = { crashes: 0, page_errors: [], visits: 0, idle_resets: 0, console_errors: 0, browser_closed_at_s: null };
page.on("crash", () => (events.crashes += 1));
// The browser process ending (closed, killed or crashed outside the page) stops the soak and fails it,
// with the time recorded, instead of ending the script without a summary.
browser.on("disconnected", () => {
  if (events.browser_closed_at_s === null) events.browser_closed_at_s = Math.round((Date.now() - started) / 1000);
});
page.on("pageerror", (e) => events.page_errors.length < 50 && events.page_errors.push(String(e).slice(0, 300)));
page.on("console", (m) => {
  if (m.type() === "error" && !/net::ERR_INTERNET_DISCONNECTED|Failed to load resource/.test(m.text())) events.console_errors += 1;
});

const started = Date.now();
await page.goto(URL);
const samples = [];

async function sample() {
  const metrics = Object.fromEntries((await cdp.send("Performance.getMetrics")).metrics.map((m) => [m.name, m.value]));
  const row = {
    t_s: Math.round((Date.now() - started) / 1000),
    heap_used_mb: +(metrics.JSHeapUsedSize / 1048576).toFixed(3),
    heap_total_mb: +(metrics.JSHeapTotalSize / 1048576).toFixed(3),
    dom_nodes: metrics.Nodes,
    listeners: metrics.JSEventListeners,
    working_set_mb: (() => {
      const b = processTreeBytes(browserPid);
      return b === null ? null : +(b / 1048576).toFixed(1);
    })(),
    visits: events.visits,
    crashes: events.crashes,
  };
  samples.push(row);
  appendFileSync(samplesPath, JSON.stringify(row) + "\n");
}

const pause = (ms) => page.waitForTimeout(ms);
const rand = (n) => Math.floor(Math.random() * n);

async function visit() {
  const start = page.getByRole("button", { name: "Touch the screen or turn the dial to start" });
  const menu = page.getByRole("heading", { name: "Choose a game" });
  // The kiosk settings load after the page: wait for either the attract screen or the menu.
  await start.or(menu).first().waitFor({ timeout: 20_000 });
  if (await start.isVisible().catch(() => false)) await start.click();
  await menu.waitFor({ timeout: 10_000 });
  const mode = ["Time Dial", "Same or Not?", "When Was This?", "Gap Hunt"][events.visits % 4];
  await page.getByRole("button", { name: new RegExp(mode.replace("?", "\\?")) }).click();
  if (mode === "Time Dial") {
    const questions = page.locator(".choice-list button");
    await questions.first().waitFor();
    await questions.nth(rand(await questions.count())).click();
    for (let i = 0; i < 30; i++) {
      await page.keyboard.press(i % 7 === 6 ? "ArrowLeft" : "ArrowRight");
      await pause(150);
    }
  } else if (mode === "Same or Not?") {
    for (let r = 0; r < 3; r++) {
      await page.getByRole("radio").nth(rand(4)).click();
      await pause(1500);
      const show = page.getByRole("button", { name: "Show the page" }).first();
      if (await show.isVisible().catch(() => false)) await show.click();
      await pause(500);
      await page.locator("[data-primary]").first().click();
      await pause(500);
    }
  } else if (mode === "When Was This?") {
    for (let r = 0; r < 3; r++) {
      for (let i = 0; i < rand(25); i++) await page.keyboard.press(Math.random() < 0.5 ? "ArrowLeft" : "ArrowRight");
      await page.locator("[data-primary]").first().click();
      await pause(1500);
      await page.locator("[data-primary]").first().click();
      await pause(500);
    }
  } else {
    const cells = page.locator("button.cell");
    await cells.first().waitFor();
    const n = await cells.count();
    for (let i = 0; i < 6; i++) {
      await cells.nth(rand(n)).click();
      await pause(700);
    }
  }
  events.visits += 1;
  if (events.visits % 5 === 0) {
    // Walk away: the kiosk must return to the attract screen on its own.
    await pause(72_000);
    if (await start.isVisible().catch(() => false)) events.idle_resets += 1;
  } else {
    await page.getByRole("button", { name: "Home" }).last().click().catch(() => undefined);
  }
}

let nextSample = Date.now();
while (Date.now() - started < HOURS * 3600_000 && events.crashes === 0 && events.browser_closed_at_s === null) {
  if (Date.now() >= nextSample) {
    await sample().catch(() => undefined);
    nextSample += SAMPLE_MS;
  }
  try {
    await visit();
  } catch (e) {
    events.page_errors.length < 50 && events.page_errors.push("visit script: " + String(e).slice(0, 200));
    await page.goto(URL).catch(() => undefined);
  }
}
if (events.browser_closed_at_s === null) await sample();

const after = samples.filter((s) => s.t_s * 1000 >= WARMUP_MS);
const heap = fit(after.map((s) => [s.t_s / 3600, s.heap_used_mb]));
const ws = fit(after.filter((s) => s.working_set_mb !== null).map((s) => [s.t_s / 3600, s.working_set_mb]));
const visitErrors = events.page_errors.filter((e) => e.startsWith("visit script:")).length;
const pass =
  events.crashes === 0 &&
  events.browser_closed_at_s === null &&
  events.page_errors.length - visitErrors === 0 &&
  heap !== null && heap.slope <= LIMITS.heap_mb_per_hour &&
  (ws === null || ws.slope <= LIMITS.working_set_mb_per_hour);
const summary = {
  url: URL, channel: CHANNEL, hours_planned: HOURS, hours_run: +((events.browser_closed_at_s ?? samples.at(-1)?.t_s ?? 0) / 3600).toFixed(2),
  network: "every host but 127.0.0.1 blocked", samples: samples.length, warmup_minutes: WARMUP_MS / 60000,
  events, limits: LIMITS,
  heap_used_mb: { first: samples[0]?.heap_used_mb, last: samples.at(-1)?.heap_used_mb, max: Math.max(...samples.map((s) => s.heap_used_mb)), slope_per_hour: heap },
  working_set_mb: { first: samples[0]?.working_set_mb, last: samples.at(-1)?.working_set_mb, slope_per_hour: ws },
  dom_nodes: { first: samples[0]?.dom_nodes, last: samples.at(-1)?.dom_nodes, max: Math.max(...samples.map((s) => s.dom_nodes)) },
  pass,
  samples_file: samplesPath,
};
writeFileSync(summaryPath, JSON.stringify(summary, null, 1) + "\n");
console.log(JSON.stringify({ pass, hours_run: summary.hours_run, visits: events.visits, crashes: events.crashes, heap: heap, ws }, null, 1));
await browser.close().catch(() => undefined);
await server.close().catch(() => undefined);
process.exit(pass ? 0 : 1);
