// The redesigned reading room in a real browser: the search is the first thing on the opening screen,
// an example topic lands on a cited answer with its scanned page, the light and dark themes both pass
// axe, a chosen theme survives a reload without a flash of the other one, the results keep the
// question box in view, and nothing is stored unless the visitor picks a theme.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const ENGINE = "https://engine.example.test";
const DATA = fileURLToPath(new URL("../../site/data/", import.meta.url));
const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
test.describe.configure({ timeout: 120_000 });

async function engineOff(page: Page): Promise<void> {
  await page.route(`${ENGINE}/**`, (route) => route.abort("connectionrefused"));
}

/** Whether the release under test includes the catalogue's data. */
async function hasCatalogue(page: Page): Promise<boolean> {
  const resp = await page.request.get("http://127.0.0.1:4173/catalogue/data/summary.json").catch(() => null);
  return !!resp && resp.ok() && (resp.headers()["content-type"] ?? "").includes("json");
}

async function violations(page: Page): Promise<string[]> {
  await page.waitForTimeout(500);
  const result = await new AxeBuilder({ page }).withTags(TAGS).exclude("iframe").analyze();
  return result.violations.flatMap((v) => v.nodes.map((n) => `${v.id} (${v.impact}): ${n.target.join(" ")}`));
}

test("the search box is on the first screen, above everything else", async ({ page }) => {
  await engineOff(page);
  await page.goto("/");
  const input = page.locator("#question");
  await expect(input).toBeVisible();
  const box = await input.boundingBox();
  const viewport = page.viewportSize()!;
  expect(box!.y + box!.height).toBeLessThan(viewport.height);
  await expect(page.getByRole("heading", { level: 1, name: "Ask Canada's public record" })).toBeVisible();
  const storage = await page.evaluate(() => localStorage.length);
  expect(storage).toBe(0);
});

test("an example topic opens a cited answer with its scanned page", async ({ page }) => {
  await engineOff(page);
  await page.goto("/");
  await page.getByRole("button", { name: /^Drug safety: / }).click();
  await expect(page.getByRole("heading", { name: "Answer from the record" })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Open the scanned page behind citation 1/ })).toBeVisible();
  await expect(page.locator("#question")).toHaveValue(/Food and Drug Directorate/);
  // The question box stays reachable at the top of the result.
  await page.mouse.wheel(0, 2500);
  await expect(page.locator(".sticky-ask")).toBeInViewport();
  // The sources can be copied as text, and the URL reproduces the answer.
  await expect(page.getByRole("button", { name: "Copy citations" })).toBeVisible();
  expect(page.url()).toContain("q=");
});

for (const scheme of ["light", "dark"] as const) {
  test(`axe finds nothing in the ${scheme} theme on the home page and an answer`, async ({ browser }) => {
    const context = await browser.newContext({ colorScheme: scheme, reducedMotion: "reduce", viewport: { width: 1280, height: 800 } });
    const page = await context.newPage();
    await engineOff(page);
    await page.goto("http://127.0.0.1:4173/");
    await expect(page.locator("html")).toHaveAttribute("data-theme", scheme);
    const found: Record<string, string[]> = { home: await violations(page) };
    await page.getByRole("button", { name: /^SARS and hospitals: / }).click();
    await expect(page.getByRole("heading", { name: "Answer from the record" })).toBeVisible();
    found.answer = await violations(page);
    expect(Object.fromEntries(Object.entries(found).filter(([, v]) => v.length))).toEqual({});
    await context.close();
  });
}

test("a chosen theme is kept, painted before the app loads, and cleared by choosing the device's", async ({ browser }) => {
  const context = await browser.newContext({ colorScheme: "dark", reducedMotion: "reduce" });
  const page = await context.newPage();
  await engineOff(page);
  // Record the theme at the first moment the document exists, before any app script runs.
  await page.addInitScript(() => {
    document.addEventListener("readystatechange", () => {
      if (document.readyState === "interactive" && !(window as unknown as { firstTheme?: string }).firstTheme) {
        (window as unknown as { firstTheme?: string | null }).firstTheme = document.documentElement.getAttribute("data-theme");
      }
    });
  });
  await page.goto("http://127.0.0.1:4173/");
  await page.getByRole("button", { name: "Switch to light theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  expect(await page.evaluate(() => localStorage.getItem("theme"))).toBe("light");
  await page.reload();
  expect(await page.evaluate(() => (window as unknown as { firstTheme?: string }).firstTheme)).toBe("light");
  const ground = await page.evaluate(() => getComputedStyle(document.documentElement).backgroundColor);
  expect(ground).toBe("rgb(245, 239, 225)");
  // The catalogue shares the choice (when this release has one: CI's release is assembled without
  // the catalogue's data, which is built from R2).
  if (await hasCatalogue(page)) {
  await page.goto("http://127.0.0.1:4173/catalogue/");
  await expect(page.getByRole("heading", { level: 1, name: "Catalogue" })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await expect(page.getByRole("button", { name: "Switch to dark theme" })).toBeVisible();
  }
  await page.goto("http://127.0.0.1:4173/");
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  expect(await page.evaluate(() => localStorage.getItem("theme"))).toBeNull();
  await context.close();
});

test("kiosk mode stays dark and stores nothing, whatever the device prefers", async ({ browser }) => {
  const context = await browser.newContext({ colorScheme: "light", reducedMotion: "reduce" });
  const page = await context.newPage();
  await engineOff(page);
  await page.goto("http://127.0.0.1:4173/?kiosk=1");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.getByTestId("theme-toggle")).toHaveCount(0);
  expect(await page.evaluate(() => localStorage.length)).toBe(0);
  await context.close();
});

test("no page scrolls sideways on a phone", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 360, height: 740 }, reducedMotion: "reduce" });
  const page = await context.newPage();
  await engineOff(page);
  for (const path of ["/", "/?view=explore", "/?view=how", "/catalogue/"]) {
    await page.goto(`http://127.0.0.1:4173${path}`);
    await page.waitForTimeout(400);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, path).toBeLessThanOrEqual(0);
  }
  await context.close();
});

test("the catalogue takes a title search from the URL, searches every decade and keeps it shareable", async ({ page }) => {
  test.skip(!(await hasCatalogue(page)), "this release was assembled without the catalogue (CI has no catalogue data)");
  await page.goto("http://127.0.0.1:4173/catalogue/?q=tuberculosis");
  await expect(page.locator("#text")).toHaveValue("tuberculosis");
  await expect(page.locator("#decade")).toHaveValue("all");
  await expect(page.locator("#count")).toContainText("documents match", { timeout: 60_000 });
  await expect(page.locator("#count")).not.toContainText("Searching", { timeout: 60_000 });
  expect(await page.locator("#results li").count()).toBeGreaterThan(0);
  await page.locator("#place").selectOption("federal");
  await expect(page).toHaveURL(/place=federal/);
  const found = await violations(page);
  expect(found).toEqual([]);
});

test("a typed question searches the whole collection, names the parts it wakes, and says which it searched", async ({ page }) => {
  const recorded = JSON.parse(readFileSync(`${DATA}pilot/answers/seed-q001.json`, "utf-8"));
  const askUrls: string[] = [];
  const healthUrls: string[] = [];
  await page.route(`${ENGINE}/**`, async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/wake") return route.fulfill({ status: 202, json: { engines: [] } });
    if (url.pathname === "/health") {
      healthUrls.push(url.search);
      const status = healthUrls.length < 2 ? "waking" : "ready";
      return route.fulfill({ json: { status, engines: [{ name: "federal-1899-1911", status, stage: null, error: null }] } });
    }
    if (url.pathname === "/ask") {
      askUrls.push(url.search);
      if (askUrls.length === 1) {
        return route.fulfill({
          status: 503,
          json: {
            status: "waking",
            retry_after_seconds: 3,
            engines: [
              { shard: "pilot", name: "pilot", status: "ready", stage: null },
              { shard: "federal-1899-1911", name: "federal-1899-1911", status: "waking", stage: { stage: "loading" } },
            ],
          },
        });
      }
      return route.fulfill({
        json: {
          ...recorded,
          answer: { ...recorded.answer, cached: null },
          router: {
            scope: "collection",
            searched: [
              { shard: "pilot", tier: null, candidates: 30 },
              { shard: "federal-1899-1911", tier: "INDEXED", candidates: 12 },
            ],
            left_out: [{ shard: "unknown-1861-1993", tier: "INDEXED", reason: "holds none of the question's words" }],
            note: "Shards left out were not searched for this question.",
          },
        },
      });
    }
    return route.fulfill({ status: 404, json: { error: "not found" } });
  });
  await page.goto("/");
  await page.locator("#question").fill("What did annual reports say about rural nursing stations?");
  await page.locator("#question").press("Enter");
  await expect(page.getByTestId("waking-parts")).toContainText("Federal public health and Federal, 1899 to 1911");
  await expect(page.getByRole("heading", { name: "Answer from the record" })).toBeVisible({ timeout: 30_000 });
  expect(askUrls[0]).toContain("scope=collection");
  expect(healthUrls[0]).toContain("scope=pilot%2Cfederal-1899-1911");
  await expect(page.getByTestId("collection-line")).toContainText("Searched across the whole collection");
  await expect(page.getByTestId("collection-line")).toContainText("Federal, 1899 to 1911");
  // No decade panel that would describe one collection's counts under a whole-collection answer.
  await expect(page.getByRole("heading", { name: "Coverage" })).toHaveCount(0);
});

test("a featured question is still served from its recording, and a collection link searches only that collection", async ({ page }) => {
  const asks: string[] = [];
  await page.route(`${ENGINE}/**`, (route) => {
    if (new URL(route.request().url()).pathname === "/ask") asks.push(route.request().url());
    return route.abort("connectionrefused");
  });
  await page.goto("/");
  await page.getByRole("button", { name: /^Drug safety: / }).click();
  await expect(page.getByRole("heading", { name: "Answer from the record" })).toBeVisible();
  expect(asks).toEqual([]);
  await page.goto("/?scope=microlog");
  await expect(page.getByTestId("scope-note")).toContainText("Searching only");
});
