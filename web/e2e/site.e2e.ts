// The static site as visitors meet it: the reading room with the engine off, a story, a recorded
// answer, and a live question while the engine wakes. The engine Worker is a route in each test.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test, type Locator, type Page } from "@playwright/test";

const ENGINE = "https://engine.example.test";
const DATA = fileURLToPath(new URL("../../site/data/", import.meta.url));
const SHOTS = fileURLToPath(new URL("../../docs/images/v2/", import.meta.url));

const stories = JSON.parse(readFileSync(`${DATA}pilot/stories.json`, "utf-8")) as { id: string; question: string; surfaces: string[] }[];
const examples = JSON.parse(readFileSync(`${DATA}pilot/examples.json`, "utf-8")) as { text: string; filters: Record<string, string> }[];
const hero = stories.find((s) => s.surfaces.includes("hero"))!;
const seed = examples[0];

/** A screenshot for the docs (SCREENSHOTS=1): the subject scrolled to the top of the view, after the
 *  archive.org page images have loaded. */
async function shot(page: Page, name: string, subject?: Locator): Promise<void> {
  if (!process.env.SCREENSHOTS) return;
  const device = test.info().project.name;
  await page.waitForLoadState("networkidle").catch(() => {});
  if (subject) await subject.evaluate((el) => el.scrollIntoView({ block: "start" }));
  await page.waitForTimeout(300);
  await page.screenshot({ path: `${SHOTS}${name}-${device}.png`, fullPage: false });
}

async function engineOff(page: Page): Promise<string[]> {
  const calls: string[] = [];
  await page.route(`${ENGINE}/**`, (route) => {
    calls.push(`${route.request().method()} ${new URL(route.request().url()).pathname}`);
    return route.abort("connectionrefused");
  });
  return calls;
}

test("the reading room works with the engine off", async ({ page }) => {
  await engineOff(page);
  await page.goto("/");
  await expect(page.getByText("Comparable and agreeing").first()).toBeVisible();
  await expect(page.locator("text=Featured pairs").first()).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await shot(page, "home");
});

test("a story opens with its comparability block, both pages and its recorded answer", async ({ page }) => {
  const calls = await engineOff(page);
  await page.goto("/");
  await page.getByRole("button", { name: `See the full answer: ${hero.question}` }).click();
  await expect(page.getByText("Comparable and agreeing").first()).toBeVisible();
  const pair = page.getByRole("region", { name: /^\d{4} and \d{4}$/ });                 // the compare view
  await expect(pair.getByRole("img", { name: /^Page image/ })).toHaveCount(2);           // both pinned pages
  await expect(page.getByText(/Recorded answer, generated/)).toBeVisible();
  expect(calls.filter((c) => c.startsWith("POST /ask"))).toEqual([]);
  await shot(page, "story", pair);
});

test("a seed question serves its recorded answer with the engine off", async ({ page }) => {
  const calls = await engineOff(page);
  const params = new URLSearchParams({ q: seed.text, ...seed.filters });
  await page.goto(`/?${params}`);
  await expect(page.getByRole("heading", { name: "Answer from the record" })).toBeVisible();
  await expect(page.getByText(/Recorded answer, generated \d{4}-\d{2}-\d{2} by claude-haiku-4-5/)).toBeVisible();
  expect(calls.filter((c) => c.startsWith("POST /ask"))).toEqual([]);
  await shot(page, "recorded-answer", page.getByRole("heading", { name: "Answer from the record" }));
});

test("a live question waits for the waking engine, keeps the question, and answers without a reload", async ({ page }) => {
  const recorded = JSON.parse(readFileSync(`${DATA}pilot/answers/seed-q001.json`, "utf-8"));
  let healthCalls = 0;
  let asks = 0;
  const wakes: string[] = [];
  await page.route(`${ENGINE}/**`, async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/wake") {
      wakes.push(url.pathname);
      return route.fulfill({ status: 202, json: { engines: [{ name: "engine", status: "waking" }] } });
    }
    if (url.pathname === "/health") {
      healthCalls += 1;
      const stage = healthCalls < 3
        ? { stage: "downloading", bytes_total: 7_700_000_000, bytes_downloaded: 2_100_000_000 * healthCalls }
        : { stage: "loading" };
      const status = healthCalls < 4 ? "waking" : "ready";
      return route.fulfill({ json: { status, engines: [{ name: "engine", status, stage, error: null }] } });
    }
    if (url.pathname === "/ask") {
      asks += 1;
      if (asks === 1) {
        return route.fulfill({ status: 503, json: { name: "engine", status: "waking", stage: { stage: "downloading", bytes_total: 7_700_000_000, bytes_downloaded: 0 } } });
      }
      return route.fulfill({ json: { ...recorded, answer: { ...recorded.answer, cached: null } } });
    }
    return route.fulfill({ status: 404, json: { error: "not found" } });
  });
  await page.goto("/");
  const box = page.locator("#question");
  await box.fill("What did annual reports say about rural nursing stations?");
  await box.press("Enter");
  await expect(page.getByRole("status").filter({ hasText: "Waking the archive engine" })).toBeVisible();
  await expect(page.getByText(/Your question is kept/)).toBeVisible();
  await shot(page, "waking", page.getByRole("status").filter({ hasText: "Waking the archive engine" }));
  await expect(page.getByRole("heading", { name: "Answer from the record" })).toBeVisible({ timeout: 30_000 });
  expect(asks).toBe(2);
  expect(wakes.length).toBe(1);                           // pre-wake on question focus, never on page load
});

test("when the engine stays down, the site says so and points to the stories", async ({ page }) => {
  await engineOff(page);
  await page.goto("/");
  await page.locator("#question").fill("What did reports say about outpost hospitals in the north?");
  await page.locator("#question").press("Enter");
  await expect(page.getByText("The archive engine is not answering right now")).toBeVisible({ timeout: 45_000 });
  await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
  await expect(page.getByText(/recorded answers, with every page cited/)).toBeVisible();
  await shot(page, "down", page.getByText("The archive engine is not answering right now"));
});
