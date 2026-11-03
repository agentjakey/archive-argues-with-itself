// The person check with the real Turnstile script, in Chromium, against Cloudflare's published test
// site keys (https://developers.cloudflare.com/turnstile/troubleshooting/testing/). Skipped unless
// TURNSTILE_CASE names the key the release was built with:
//
//   VITE_TURNSTILE_SITEKEY=<key> npm run build:e2e
//   python scripts/v2/build_release.py assemble --release-id e2e --api-origin https://engine.example.test
//   TURNSTILE_CASE=<case> npx playwright test e2e/turnstile.e2e.ts
//
//   invisible-pass  1x00000000000000000000BB   Invisible widget, passes
//   managed-pass    1x00000000000000000000AA   visible (Managed-style) widget, passes
//   invisible-fail  2x00000000000000000000BB   Invisible widget, fails
//   managed-fail    2x00000000000000000000AB   visible widget, fails
//   interactive     3x00000000000000000000FF   visible widget that needs a click
//
// Needs the network (challenges.cloudflare.com). The engine Worker is a route that accepts only a
// request carrying a token; with Cloudflare's test keys the token is the documented dummy one.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";

const ENGINE = "https://engine.example.test";
const DATA = fileURLToPath(new URL("../../site/data/", import.meta.url));
const SHOTS = fileURLToPath(new URL("../../docs/images/v2/", import.meta.url));
const CASE = process.env.TURNSTILE_CASE ?? "";
const QUESTION = "What did annual reports say about rural nursing stations?";

test.skip(!CASE, "TURNSTILE_CASE is not set: build with a Turnstile test key first");
test.describe.configure({ timeout: 120_000 });

async function engine(page: Page, tokens: string[], answerStatus = 200): Promise<void> {
  const recorded = JSON.parse(readFileSync(`${DATA}pilot/answers/seed-q001.json`, "utf-8"));
  await page.route(`${ENGINE}/**`, async (route) => {
    const url = new URL(route.request().url());
    const token = (await route.request().allHeaders())["x-turnstile-token"];
    if (url.pathname === "/wake") return route.fulfill({ status: 202, json: { engines: [] } });
    if (url.pathname === "/health") return route.fulfill({ json: { status: "ready", engines: [] } });
    if (url.pathname === "/ask") {
      tokens.push(token ?? "");
      if (!token) return route.fulfill({ status: 403, json: { error: "turnstile_missing" } });
      if (answerStatus !== 200) return route.fulfill({ status: answerStatus, json: { error: "turnstile_failed" } });
      return route.fulfill({ json: { ...recorded, answer: { ...recorded.answer, cached: null } } });
    }
    return route.fulfill({ status: 404, json: { error: "not found" } });
  });
}

/** The size the widget takes up in the slot beside Ask. */
async function slotHeight(page: Page): Promise<number> {
  return (await page.locator("#turnstile-slot").boundingBox())?.height ?? 0;
}

async function shot(page: Page, name: string): Promise<void> {
  if (process.env.SCREENSHOTS) await page.screenshot({ path: `${SHOTS}turnstile-${name}-${test.info().project.name}.png` });
}

test("a question gets through, or gets a plain message and a retry", async ({ page }) => {
  const tokens: string[] = [];
  await engine(page, tokens);
  await page.goto("/");
  const box = page.locator("#question");
  await box.fill(QUESTION);
  await box.press("Enter");

  if (CASE.endsWith("-pass")) {
    // the loading skeleton shares the answer's heading; the line beside a written answer does not
    await expect(page.getByText(/^Written by an AI model/)).toBeVisible({ timeout: 60_000 });
    expect(tokens.filter(Boolean).length).toBeGreaterThan(0);
    expect(tokens.every((t) => t === "XXXX.DUMMY.TOKEN.XXXX")).toBe(true);
    // Interaction-only: nothing is drawn for a visitor who passes without a click.
    expect(await slotHeight(page)).toBeLessThan(10);
    await shot(page, CASE);
  } else if (CASE.endsWith("-fail")) {
    await expect(page.getByText("We could not confirm that this question came from a person")).toBeVisible({ timeout: 60_000 });
    await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
    expect(tokens).toEqual([]);                                     // nothing was sent
    await shot(page, CASE);
    await page.getByRole("button", { name: "Try again" }).click();  // the retry runs a fresh check
    await expect(page.getByText("We could not confirm that this question came from a person")).toBeVisible({ timeout: 60_000 });
  } else if (CASE === "interactive") {
    // The challenge appears in the slot right under Ask, with a plain hint, and waits for the visitor.
    await expect(page.getByText(/Cloudflare asks you to confirm you are a person/)).toBeVisible({ timeout: 60_000 });
    await expect.poll(() => slotHeight(page), { timeout: 30_000 }).toBeGreaterThan(40);
    const slot = await page.locator("#turnstile-slot").boundingBox();
    const ask = await page.locator('form button[type="submit"]').boundingBox();
    expect(slot && ask && slot.y >= ask.y).toBe(true);              // just below the button, on screen
    expect(slot!.y).toBeLessThan(page.viewportSize()!.height);
    await shot(page, CASE);
  } else {
    throw new Error(`unknown TURNSTILE_CASE ${CASE}`);
  }
});

test("a token the engine refuses gets the same plain message", async ({ page }) => {
  test.skip(!CASE.endsWith("-pass"), "needs a passing key");
  const tokens: string[] = [];
  await engine(page, tokens, 403);
  await page.goto("/");
  await page.locator("#question").fill(QUESTION);
  await page.locator("#question").press("Enter");
  await expect(page.getByText("We could not confirm that this question came from a person")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("turnstile_failed")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
});
