// The redesigned reading room in a real browser: the search is the first thing on the opening screen,
// an example topic lands on a cited answer with its scanned page, the light and dark themes both pass
// axe, a chosen theme survives a reload without a flash of the other one, the results keep the
// question box in view, and nothing is stored unless the visitor picks a theme.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const ENGINE = "https://engine.example.test";
const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
test.describe.configure({ timeout: 120_000 });

async function engineOff(page: Page): Promise<void> {
  await page.route(`${ENGINE}/**`, (route) => route.abort("connectionrefused"));
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
  await expect(page.getByRole("heading", { level: 1, name: "Ask Canada's public-health record" })).toBeVisible();
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
  // The catalogue shares the choice.
  await page.goto("http://127.0.0.1:4173/catalogue/");
  await expect(page.getByRole("heading", { level: 1, name: "Catalogue" })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await expect(page.getByRole("button", { name: "Switch to dark theme" })).toBeVisible();
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
