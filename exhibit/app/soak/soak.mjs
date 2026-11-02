// The kiosk soak test: hours of scripted visits against the kiosk server with every outside host
// blocked (as a library kiosk with no network), sampling memory once a minute.
//
//   node soak/soak.mjs --hours 8 --url http://127.0.0.1:8765/exhibit/ --out ../../reports/v2/exhibit/soak
//   node soak/soak.mjs --hours 0.05 --warmup-minutes 0.5 --sample-seconds 10 --channel chromium --headless true
//
// The second form is the short smoke run (three minutes) that also runs on a Linux CI runner with
// Playwright's own Chromium, headless. On Windows the default is the kiosk's browser (Edge), with a
// window. Each visit plays the kiosk the way a visitor would: one tap from the attract screen
// through the rounds to the chronicle, a group visit with secret votes, or Gap Hunt from "All
// games"; every fifth visit walks away and waits for the kiosk to return to the attract screen.
//
// Each sample records the page's JS heap and DOM node count (Chrome DevTools Protocol) and the
// memory of the browser and all its child processes (Windows: working set from Win32_Process;
// Linux: resident set from /proc). The summary
// fits a straight line to the samples after the first hour, and reports the slope per hour with its
// standard error, every page crash and every uncaught page error. It passes when nothing crashed,
// nothing threw, and neither the heap nor the working set grew by more than the stated limits per
// hour. The limits are written into the summary with the result.
// A run planned for under an hour is a smoke run, judged differently (see SMOKE below).
import { chromium } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { appendFileSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, a, i, all) => (a.startsWith("--") ? [...acc, [a.slice(2), all[i + 1]]] : acc), []),
);
const HOURS = Number(args.hours ?? 8);
const URL = args.url ?? "http://127.0.0.1:8765/exhibit/";
const OUT = args.out ?? "../../reports/v2/exhibit/soak";
const WINDOWS = process.platform === "win32";
const CHANNEL = args.channel ?? (WINDOWS ? "msedge" : "chromium");   // the kiosk's browser; Chromium on CI
const HEADLESS = (args.headless ?? (WINDOWS ? "false" : "true")) === "true";
const SAMPLE_MS = Number(args["sample-seconds"] ?? 60) * 1000;
const WARMUP_MS = Number(args["warmup-minutes"] ?? 60) * 60_000;
const LIMITS = { heap_mb_per_hour: 1.0, working_set_mb_per_hour: 10.0, smoke_heap_ceiling_mb: 64 };

const stamp = new Date().toISOString().replace(/[:.]/g, "-");
mkdirSync(OUT, { recursive: true });
const samplesPath = join(OUT, `soak-${stamp}.jsonl`);
const summaryPath = join(OUT, `soak-${stamp}-summary.json`);

// Resident memory of a process and all its descendants on Linux, read from /proc.
function linuxTreeBytes(rootPid) {
  try {
    const parent = new Map();
    for (const name of readdirSync("/proc")) {
      if (!/^[0-9]+$/.test(name)) continue;
      try {
        const stat = readFileSync(`/proc/${name}/stat`, "utf8");
        const fields = stat.slice(stat.lastIndexOf(")") + 2).split(" ");
        parent.set(Number(name), Number(fields[1]));
      } catch {
        // the process ended while we looked
      }
    }
    const tree = new Set([rootPid]);
    let added = true;
    while (added) {
      added = false;
      for (const [pid, ppid] of parent) {
        if (tree.has(ppid) && !tree.has(pid)) {
          tree.add(pid);
          added = true;
        }
      }
    }
    let total = 0;
    for (const pid of tree) {
      try {
        const line = readFileSync(`/proc/${pid}/status`, "utf8").split("\n").find((l) => l.startsWith("VmRSS:"));
        if (line) total += Number(line.replace(/[^0-9]/g, "")) * 1024;
      } catch {
        // gone
      }
    }
    return total;
  } catch {
    return null;
  }
}

function processTreeBytes(rootPid) {
  if (!rootPid) return null;
  if (process.platform === "linux") return linuxTreeBytes(rootPid);
  if (!WINDOWS) return null;
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

const server = await chromium.launchServer({
  ...(CHANNEL === "chromium" ? {} : { channel: CHANNEL }),
  headless: HEADLESS,
  args: ["--kiosk-printing"],
});
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

const primary = () => page.locator("[data-primary]").first();

// One visit through the rounds, from the first round to the chronicle. With players set, every Same
// or Not? round is voted on in secret by that many players, passing the screen along.
async function playRounds(players) {
  for (let i = 0; i < 10; i++) {
    const kind = await page.locator("[data-step]").first().getAttribute("data-step", { timeout: 15_000 });
    if (kind === "chronicle") {
      const use = page.getByRole("button", { name: "Use this" });
      const n = await use.count();
      if (n > 0) await use.nth(rand(n)).click();
      await pause(800);
      return;
    }
    if (kind === "when_was_this") {
      const turns = rand(25);
      for (let k = 0; k < turns; k++) await page.keyboard.press(Math.random() < 0.5 ? "ArrowLeft" : "ArrowRight");
      await page.getByRole("button", { name: "Lock it in" }).click();
      if (Math.random() < 0.3) await page.getByRole("button", { name: "How do we know?" }).click();
    } else if (kind === "same_or_not") {
      if (Math.random() < 0.3) {
        await page.getByRole("button", { name: "Read page A" }).click();
        await pause(400);
        await page.getByRole("button", { name: "Back to the claims" }).click();
      }
      for (let p = 1; p <= (players ?? 1); p++) {
        await page.getByRole("radio").nth(rand(4)).click();
        if (players && p < players) await page.getByRole("button", { name: `I am player ${p + 1}` }).click();
      }
    } else if (kind === "time_dial") {
      for (let k = 0; k < 30; k++) {
        await page.keyboard.press(k % 7 === 6 ? "ArrowLeft" : "ArrowRight");
        await pause(100);
      }
    }
    await primary().click({ timeout: 15_000 });
    await pause(300);
  }
}

async function visit() {
  const start = page.getByRole("button", { name: "Touch to start" });
  // The kiosk settings and the deck load after the page: wait for the attract screen.
  await start.waitFor({ timeout: 20_000 });
  const kind = events.visits % 4;
  if (kind === 2) {
    await page.getByRole("button", { name: "All games" }).click();
    await page.getByRole("button", { name: /Gap Hunt/ }).click();
    const cells = page.locator("button.cell");
    await cells.first().waitFor();
    const n = await cells.count();
    for (let i = 0; i < 6; i++) {
      await cells.nth(rand(n)).click();
      await pause(500);
    }
  } else if (kind === 3) {
    await page.getByRole("button", { name: "Play as a group" }).click();
    const players = 2 + rand(3);
    await page.getByRole("button", { name: `${players} players` }).click();
    await playRounds(players);
  } else {
    await start.click();
    await playRounds(null);
  }
  events.visits += 1;
  if (events.visits % 5 === 0) {
    // Walk away: the kiosk must return to the attract screen on its own.
    await pause(72_000);
    if (await start.isVisible().catch(() => false)) events.idle_resets += 1;
  } else {
    await page.getByRole("button", { name: "Start over" }).click().catch(() => undefined);
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
// A run of under an hour (the CI smoke run) is too short for a per-hour memory slope to mean
// anything, so it is judged on what it can show: no crash, no page error, no step of the visit
// script failing, at least three whole visits, the kiosk back on the attract screen after every
// walk-away, and the JS heap staying under a fixed ceiling. The slopes are still reported.
const SMOKE = HOURS < 1;
const walkAways = Math.floor(events.visits / 5);
const heapMax = Math.max(...samples.map((s) => s.heap_used_mb));
const pass = SMOKE
  ? events.crashes === 0 &&
    events.browser_closed_at_s === null &&
    events.page_errors.length === 0 &&
    events.visits >= 3 &&
    events.idle_resets === walkAways &&
    heapMax <= LIMITS.smoke_heap_ceiling_mb
  : events.crashes === 0 &&
    events.browser_closed_at_s === null &&
    events.page_errors.length - visitErrors === 0 &&
    heap !== null && heap.slope <= LIMITS.heap_mb_per_hour &&
    (ws === null || ws.slope <= LIMITS.working_set_mb_per_hour);
const summary = {
  url: URL, channel: CHANNEL, headless: HEADLESS, platform: process.platform, hours_planned: HOURS, sample_seconds: SAMPLE_MS / 1000, hours_run: +((events.browser_closed_at_s ?? samples.at(-1)?.t_s ?? 0) / 3600).toFixed(2),
  network: "every host but 127.0.0.1 blocked", samples: samples.length, warmup_minutes: WARMUP_MS / 60000,
  events, limits: LIMITS,
  heap_used_mb: { first: samples[0]?.heap_used_mb, last: samples.at(-1)?.heap_used_mb, max: Math.max(...samples.map((s) => s.heap_used_mb)), slope_per_hour: heap },
  working_set_mb: { first: samples[0]?.working_set_mb, last: samples.at(-1)?.working_set_mb, slope_per_hour: ws },
  dom_nodes: { first: samples[0]?.dom_nodes, last: samples.at(-1)?.dom_nodes, max: Math.max(...samples.map((s) => s.dom_nodes)) },
  mode: SMOKE ? "smoke (under one hour: slopes reported, not judged)" : "soak",
  walk_aways: walkAways,
  pass,
  samples_file: samplesPath,
};
writeFileSync(summaryPath, JSON.stringify(summary, null, 1) + "\n");
console.log(JSON.stringify({ pass, hours_run: summary.hours_run, visits: events.visits, crashes: events.crashes, heap: heap, ws }, null, 1));
await browser.close().catch(() => undefined);
await server.close().catch(() => undefined);
process.exit(pass ? 0 : 1);
