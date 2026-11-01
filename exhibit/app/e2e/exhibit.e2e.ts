// The exhibit end to end, as the kiosk serves it, at kiosk size (1920x1080, touch) and phone size:
// every mode plays through with real deck rounds, passes axe (WCAG 2.1 A and AA rules), works from
// the keyboard alone, keeps working with the network cut, and stores nothing in the browser.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";

const SHOTS = process.env.SCREENSHOTS === "1";
const SHOT_DIR = "../../docs/images/exhibit";

async function shot(page: Page, name: string, project: string) {
  if (!SHOTS) return;
  mkdirSync(SHOT_DIR, { recursive: true });
  await page.screenshot({ path: `${SHOT_DIR}/${project}-${name}.png`, fullPage: false });
}

async function axe(page: Page, where: string) {
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const summary = result.violations.map((v) => `${v.id}: ${v.nodes.length} (${v.help})`);
  expect(summary, `axe violations on ${where}`).toEqual([]);
}

async function start(page: Page) {
  await page.goto("/exhibit/");
  await page.getByRole("button", { name: "Touch the screen or turn the dial to start" }).click();
  await expect(page.getByRole("heading", { name: "Choose a game" })).toBeVisible();
}

test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
});

test("attract screen and menu", async ({ page }, info) => {
  await page.goto("/exhibit/");
  await expect(page.getByText("No personal data is collected. Nothing is stored.")).toBeVisible();
  await shot(page, "attract", info.project.name);
  await axe(page, "attract");
  await page.getByRole("button", { name: "Touch the screen or turn the dial to start" }).click();
  await shot(page, "menu", info.project.name);
  await axe(page, "menu");
});

test("Time Dial", async ({ page }, info) => {
  await start(page);
  await page.getByRole("button", { name: /Time Dial/ }).click();
  await page.locator(".choice-list button").first().click();
  const slider = page.getByRole("slider", { name: "Year" });
  await expect(slider).toBeVisible();
  await slider.focus();
  await page.keyboard.press("End");
  await expect(page.locator(".answer")).toContainText(/Built from \d+ pages? published by \d{4}\./);
  await shot(page, "time-dial", info.project.name);
  await axe(page, "time dial");
  await page.keyboard.press("Home");
  await expect(page.locator(".year-line")).toContainText("1960");
});

test("Same or Not?", async ({ page }, info) => {
  await start(page);
  await page.getByRole("button", { name: /Same or Not\?/ }).click();
  await expect(page.getByText("Claim from page A")).toBeVisible();
  await shot(page, "same-or-not", info.project.name);
  await axe(page, "same or not");
  await page.getByRole("radio").first().click();
  await expect(page.locator(".reveal-head")).toContainText("The answer:");
  await expect(page.locator(".page mark").first()).toBeVisible();
  await shot(page, "same-or-not-reveal", info.project.name);
  await axe(page, "same or not reveal");
});

test("When Was This?", async ({ page }, info) => {
  await start(page);
  await page.getByRole("button", { name: /When Was This\?/ }).click();
  const text = await page.locator(".page-text").innerText();
  expect(text).not.toMatch(/(?<![0-9])(19[0-9]{2}|20[0-2][0-9])(?![0-9])/);
  await shot(page, "when-was-this", info.project.name);
  await axe(page, "when was this");
  await page.getByRole("button", { name: "Lock in my guess" }).click();
  await expect(page.locator(".reveal-head")).toContainText("Published in");
  await expect(page.getByText("How we know the year")).toBeVisible();
  await shot(page, "when-was-this-reveal", info.project.name);
  await axe(page, "when was this reveal");
});

test("Gap Hunt", async ({ page }, info) => {
  await start(page);
  await page.getByRole("button", { name: /Gap Hunt/ }).click();
  await page.locator("button.cell").first().click();
  await expect(page.locator(".gap-explain")).not.toBeEmpty();
  await shot(page, "gap-hunt", info.project.name);
  await axe(page, "gap hunt");
});

test("French", async ({ page }, info) => {
  await start(page);
  await page.getByRole("button", { name: "Fran\u00e7ais" }).click();
  await expect(page.getByRole("heading", { name: "Choisissez un jeu" })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "fr");
  await shot(page, "menu-fr", info.project.name);
  await axe(page, "menu in French");
});

test("keyboard only: every mode", async ({ page }) => {
  await page.goto("/exhibit/");
  await expect(page.getByRole("button", { name: "Touch the screen or turn the dial to start" })).toBeVisible();
  await page.keyboard.press("Enter");                       // the dial's press starts the visit
  await expect(page.getByRole("heading", { name: "Choose a game" })).toBeVisible();
  for (const mode of ["Time Dial", "Same or Not?", "When Was This?", "Gap Hunt"]) {
    let found = false;
    for (let i = 0; i < 30 && !found; i++) {
      await page.keyboard.press("Tab");
      found = (await page.evaluate(() => document.activeElement?.textContent ?? "")).startsWith(mode);
    }
    expect(found, `reached ${mode} by Tab`).toBe(true);
    await page.keyboard.press("Enter");
    await expect(page.locator("main h2").first()).toBeVisible();
    if (mode === "When Was This?") {
      await page.keyboard.press("ArrowRight");                // the dial turns with nothing focused in a control
      await page.keyboard.press("Escape");
      await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
      await page.keyboard.press("Enter");                   // the dial's press locks the guess
      await expect(page.locator(".reveal-head")).toContainText("Published in");
    }
    const home = page.getByRole("button", { name: "Home" }).last();
    await home.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { name: "Choose a game" })).toBeVisible();
  }
});

test("works offline and stores nothing", async ({ page, context }) => {
  await start(page);
  await context.setOffline(true);
  await page.getByRole("button", { name: /Same or Not\?/ }).click();
  await page.getByRole("button", { name: "Show the page" }).first().click();
  await expect(page.getByText(/The page image needs a connection/)).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".page-text").first()).not.toBeEmpty();
  const stored = await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length, cookies: document.cookie }));
  expect(stored).toEqual({ local: 0, session: 0, cookies: "" });
  await context.setOffline(false);
});

test("a full visit", async ({ browser }, info) => {
  test.skip(info.project.name !== "kiosk", "recorded once, at kiosk size");
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    recordVideo: { dir: "test-results/visit", size: { width: 1280, height: 720 } },
    reducedMotion: "no-preference",
  });
  const page = await context.newPage();
  await page.goto("/exhibit/");
  await page.waitForTimeout(3000);
  await page.getByRole("button", { name: "Touch the screen or turn the dial to start" }).click();
  await page.getByRole("button", { name: /Time Dial/ }).click();
  await page.locator(".choice-list button").first().click();
  for (let i = 0; i < 40; i++) {
    await page.keyboard.press("ArrowRight");
    await page.waitForTimeout(120);
  }
  await page.getByRole("button", { name: "Home" }).last().click();
  await page.getByRole("button", { name: /Same or Not\?/ }).click();
  await page.waitForTimeout(2500);
  await page.getByRole("radio").nth(2).click();
  await page.waitForTimeout(3000);
  await page.getByRole("button", { name: "Home" }).last().click();
  await page.getByRole("button", { name: /When Was This\?/ }).click();
  await page.waitForTimeout(2000);
  for (let i = 0; i < 12; i++) {
    await page.keyboard.press("ArrowLeft");
    await page.waitForTimeout(100);
  }
  await page.getByRole("button", { name: "Lock in my guess" }).click();
  await page.waitForTimeout(3000);
  await page.getByRole("button", { name: "Home" }).last().click();
  await page.getByRole("button", { name: /Gap Hunt/ }).click();
  await page.locator("button.cell").nth(10).click();
  await page.waitForTimeout(2500);
  await context.close();
});
