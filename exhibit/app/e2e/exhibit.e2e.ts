// The exhibit end to end, as the kiosk serves it, at kiosk size (1920x1080, touch), at 3840x2160 and
// at phone size (390x844): every screen of a visit with real deck rounds, axe on every screen (no
// serious or critical WCAG 2.x A/AA violation, and no AAA contrast failure), a whole visit from the
// keyboard alone, the group vote, the network cut, nothing stored in the browser, and one recorded
// visit. With EVIDENCE=<folder>, screenshots, axe results and the video are written there.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type TestInfo } from "@playwright/test";
import { appendFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";

const EVIDENCE = process.env.EVIDENCE ?? "";
const AA_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

async function shot(page: Page, info: TestInfo, name: string) {
  if (!EVIDENCE) return;
  await page.waitForTimeout(400); // let a reveal's scroll into view settle before the picture
  const dir = join(EVIDENCE, "screens", info.project.name);
  mkdirSync(dir, { recursive: true });
  await page.screenshot({ path: join(dir, `${name}.png`), fullPage: false });
}

// axe on the screen as it stands: WCAG 2.x A and AA rules, plus the AAA contrast rule
// (color-contrast-enhanced: 7:1 for body text, 4.5:1 for large text).
async function axe(page: Page, info: TestInfo, where: string) {
  const result = await new AxeBuilder({ page }).withTags([...AA_TAGS, "wcag2aaa"]).analyze();
  const rows = result.violations.map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.length, help: v.help }));
  if (EVIDENCE) {
    mkdirSync(EVIDENCE, { recursive: true });
    appendFileSync(
      join(EVIDENCE, "axe.jsonl"),
      JSON.stringify({ project: info.project.name, screen: where, passes: result.passes.length, violations: rows }) + "\n",
    );
  }
  const blocking = rows.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking, `serious or critical axe violations on ${where}`).toEqual([]);
  const contrast = rows.filter((v) => v.id === "color-contrast" || v.id === "color-contrast-enhanced");
  expect(contrast, `contrast failures on ${where}`).toEqual([]);
}

async function look(page: Page, info: TestInfo, name: string) {
  await shot(page, info, name);
  await axe(page, info, name);
}

const start = (page: Page) => page.getByRole("button", { name: "Touch to start" });
const step = (page: Page) => page.locator("[data-step]").first();

test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
});

test("every screen of a visit", async ({ page }, info) => {
  await page.goto("/exhibit/");
  await expect(page.getByText("No personal data is collected. Nothing is stored.")).toBeVisible();
  await expect(start(page)).toBeVisible();
  await look(page, info, "01-attract");

  await start(page).click();
  const seen = new Set<string>();
  for (let i = 0; i < 6; i++) {
    const kind = await step(page).getAttribute("data-step");
    if (kind === "chronicle") break;
    const first = !seen.has(kind ?? "");
    seen.add(kind ?? "");
    const tag = `${String(i + 2).padStart(2, "0")}-${kind}`;
    if (first) await look(page, info, tag);
    if (kind === "when_was_this") {
      const text = await page.locator(".page-text").innerText();
      expect(text).not.toMatch(/(?<![0-9])(19[0-9]{2}|20[0-2][0-9])(?![0-9])/);
      await page.getByRole("button", { name: "Lock it in" }).click();
      await expect(page.locator(".verdict")).toContainText("Published in");
      await expect(page.getByText(/Checked by AI against the pages; human review pending/)).toBeVisible();
      if (first) {
        await page.getByRole("button", { name: "How do we know?" }).click();
        await look(page, info, `${tag}-reveal`);
      }
    } else if (kind === "same_or_not") {
      if (first) {
        await page.getByRole("button", { name: "Read page A" }).click();
        await expect(page.getByRole("button", { name: "Back to the claims" })).toBeVisible();
        await look(page, info, `${tag}-page`);
        await page.getByRole("button", { name: "Back to the claims" }).click();
      }
      await page.getByRole("radio").nth(2).click();
      await expect(page.locator(".verdict")).toContainText("The answer:");
      await expect(page.locator(".checklist")).toBeVisible();
      if (first) await look(page, info, `${tag}-reveal`);
    } else if (kind === "time_dial") {
      const slider = page.getByRole("slider", { name: "Year" });
      await slider.focus();
      await page.keyboard.press("End");
      await expect(page.locator(".answer")).toContainText(/Built from \d+ pages? published by \d{4}\./);
      await look(page, info, `${tag}-end`);
    }
    await page.locator("[data-primary]").first().click();
  }
  await expect(page.getByRole("heading", { name: "Your visit" })).toBeVisible();
  await expect(page.getByRole("article", { name: "Evidence card" })).toBeVisible();
  await look(page, info, "08-chronicle");

  await page.getByRole("button", { name: "Start over" }).click();
  await page.getByRole("button", { name: "All games" }).click();
  await look(page, info, "09-menu");
  await page.getByRole("button", { name: /Gap Hunt/ }).click();
  await page.locator("button.cell").first().click();
  await expect(page.locator(".gap-explain")).not.toBeEmpty();
  await look(page, info, "10-gap-hunt");
  await page.getByRole("button", { name: "Start over" }).click();
  await page.getByRole("button", { name: "All games" }).click();
  await page.getByRole("button", { name: /Time Dial/ }).click();
  await look(page, info, "11-time-dial-questions");

  await page.getByRole("button", { name: "Start over" }).click();
  await page.getByRole("button", { name: /Fran/ }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "fr");
  await expect(page.getByText(/Texte fran.ais r.dig. par IA/)).toBeVisible();
  await look(page, info, "12-attract-fr");
});

test("group mode: secret picks, then the split bar", async ({ page }, info) => {
  await page.goto("/exhibit/");
  await page.getByRole("button", { name: "Play as a group" }).click();
  await look(page, info, "13-players");
  await page.getByRole("button", { name: "3 players" }).click();
  await page.getByRole("button", { name: "Lock it in" }).click();
  await page.locator("[data-primary]").first().click();
  await expect(page.getByText("Player 1 of 3, pick in secret", { exact: false })).toBeVisible();
  await page.getByRole("radio").nth(2).click();
  await expect(page.getByRole("heading", { name: "Pass the screen to player 2" })).toBeVisible();
  await look(page, info, "14-group-pass");
  await page.getByRole("button", { name: "I am player 2" }).click();
  await page.getByRole("radio").nth(2).click();
  await page.getByRole("button", { name: "I am player 3" }).click();
  await page.getByRole("radio").nth(0).click();
  await expect(page.getByRole("img", { name: /How the room voted/ })).toBeVisible();
  await expect(page.locator(".split-result")).toContainText(/of 3 picked the answer\./);
  await look(page, info, "15-group-split");
});

test("keyboard only: a whole visit, attract to chronicle", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "a phone has no keyboard; checked at kiosk and 4K size");
  await page.goto("/exhibit/");
  await expect(start(page)).toBeVisible();
  await page.keyboard.press("Enter"); // the dial's press starts the visit
  for (let i = 0; i < 6; i++) {
    const kind = await step(page).getAttribute("data-step");
    if (kind === "chronicle") break;
    if (kind === "when_was_this") {
      for (let k = 0; k < 7; k++) await page.keyboard.press("ArrowLeft"); // the dial turns with nothing focused
      await page.keyboard.press("Enter"); // the dial's press locks the guess
      await expect(page.locator(".verdict")).toContainText("Published in");
    } else if (kind === "same_or_not") {
      let onChoice = false;
      for (let k = 0; k < 20 && !onChoice; k++) {
        await page.keyboard.press("Tab");
        onChoice = (await page.evaluate(() => document.activeElement?.getAttribute("role"))) === "radio";
      }
      expect(onChoice, "reached the choices by Tab").toBe(true);
      await page.keyboard.press("ArrowDown");
      await page.keyboard.press("Enter");
      await expect(page.locator(".verdict")).toContainText("The answer:");
    } else if (kind === "time_dial") {
      for (let k = 0; k < 12; k++) await page.keyboard.press("ArrowRight");
      await expect(page.locator(".year-line")).not.toBeEmpty();
    }
    await page.keyboard.press("Enter"); // Next, the screen's main action
    await expect(step(page)).toBeVisible();
  }
  await expect(page.getByRole("heading", { name: "Your visit" })).toBeVisible();
  let onUse = false;
  for (let k = 0; k < 30 && !onUse; k++) {
    await page.keyboard.press("Tab");
    onUse = ((await page.evaluate(() => document.activeElement?.textContent)) ?? "").trim() === "Use this";
  }
  expect(onUse, "reached a chronicle row by Tab").toBe(true);
  await page.keyboard.press("Enter");
  await expect(page.locator("[aria-pressed='true']", { hasText: "On your card" })).toBeVisible();
  if (EVIDENCE) {
    mkdirSync(EVIDENCE, { recursive: true });
    appendFileSync(join(EVIDENCE, "keyboard.jsonl"), JSON.stringify({ project: info.project.name, result: "full visit by keyboard: passed" }) + "\n");
  }
});

test("works offline and stores nothing", async ({ page, context }) => {
  await page.goto("/exhibit/");
  await start(page).click();
  await context.setOffline(true);
  await page.getByRole("button", { name: "Show the scan" }).first().click();
  await expect(page.getByText(/The scan needs a connection/)).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".page-text").first()).not.toBeEmpty();
  const stored = await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length, cookies: document.cookie }));
  expect(stored).toEqual({ local: 0, session: 0, cookies: "" });
  await context.setOffline(false);
});

test("a full visit, recorded", async ({ browser }, info) => {
  test.skip(info.project.name !== "kiosk", "recorded once, at kiosk size");
  const dir = EVIDENCE ? join(EVIDENCE, "video") : "test-results/visit";
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    recordVideo: { dir, size: { width: 1280, height: 720 } },
    reducedMotion: "no-preference",
  });
  const page = await context.newPage();
  const began = Date.now();
  await page.goto("/exhibit/");
  await page.waitForTimeout(2500);
  await start(page).click();
  for (let i = 0; i < 6; i++) {
    const kind = await step(page).getAttribute("data-step");
    if (kind === "chronicle") break;
    await page.waitForTimeout(2000);
    if (kind === "when_was_this") {
      for (let k = 0; k < 9; k++) {
        await page.keyboard.press(i === 0 ? "ArrowLeft" : "ArrowRight");
        await page.waitForTimeout(140);
      }
      await page.getByRole("button", { name: "Lock it in" }).click();
    } else if (kind === "same_or_not") {
      await page.getByRole("radio").nth(2).click();
    } else if (kind === "time_dial") {
      for (let k = 0; k < 30; k++) {
        await page.keyboard.press("ArrowRight");
        await page.waitForTimeout(150);
      }
    }
    await page.locator("[data-primary]").first().waitFor();
    await page.waitForTimeout(4500);
    await page.locator("[data-primary]").first().click();
  }
  await expect(page.getByRole("heading", { name: "Your visit" })).toBeVisible();
  await page.waitForTimeout(4000);
  const seconds = (Date.now() - began) / 1000;
  await context.close();
  expect(seconds).toBeLessThan(90);
  if (EVIDENCE) appendFileSync(join(EVIDENCE, "video.jsonl"), JSON.stringify({ seconds: Math.round(seconds), dir }) + "\n");
});
