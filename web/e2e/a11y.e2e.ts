// Accessibility checks of the assembled static release: axe-core (WCAG 2.0, 2.1 and 2.2, A and AA)
// on every page, on an answer, on a story and on the page drawer, and a keyboard pass through the
// main paths. Runs at phone and laptop width (playwright.config.ts). SCREENSHOTS=1 also saves each
// policy page to docs/images/v2/.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const ENGINE = "https://engine.example.test";
const DATA = fileURLToPath(new URL("../../site/data/", import.meta.url));
const SHOTS = fileURLToPath(new URL("../../docs/images/v2/", import.meta.url));
const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
const VIEWS = ["explore", "how", "gaps", "sources", "map", "timeline", "about", "privacy", "terms", "accessibility", "corrections"];
test.describe.configure({ timeout: 300_000 });

const POLICY = ["about", "privacy", "terms", "accessibility", "corrections"];

const examples = JSON.parse(readFileSync(`${DATA}pilot/examples.json`, "utf-8")) as { text: string; filters: Record<string, string> }[];
const stories = JSON.parse(readFileSync(`${DATA}pilot/stories.json`, "utf-8")) as { question: string; surfaces: string[] }[];
const seed = examples[0];
const hero = stories.find((s) => s.surfaces.includes("hero"))!;

async function engineOff(page: Page): Promise<void> {
  await page.route(`${ENGINE}/**`, (route) => route.abort("connectionrefused"));
}

/** Every axe violation on the page as it is now, as "rule: target" lines (empty when clean). The
 *  archive.org page images and viewer are outside this site, so their frames are not checked. */
async function violations(page: Page): Promise<string[]> {
  await page.waitForTimeout(500);
  const result = await new AxeBuilder({ page }).withTags(TAGS).exclude("iframe").analyze();
  return result.violations.flatMap((v) => v.nodes.map((n) => `${v.id} (${v.impact}): ${n.target.join(" ")}`));
}

/** Whether the focused element shows a focus indicator (an outline or a ring). */
async function focusVisible(page: Page): Promise<boolean> {
  return page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    if (!el || el === document.body) return false;
    const style = getComputedStyle(el);
    return (style.outlineStyle !== "none" && parseFloat(style.outlineWidth) > 0) || style.boxShadow !== "none";
  });
}

test("axe finds nothing on the home page and every reading page", async ({ page }) => {
  await engineOff(page);
  await page.goto("/");
  await expect(page.locator("#question")).toBeVisible();
  const found: Record<string, string[]> = { home: await violations(page) };
  for (const view of VIEWS) {
    await page.goto(`/?view=${view}`);
    await expect(page.locator("#page-heading, #main-content").first()).toBeVisible();
    found[view] = await violations(page);
    if (process.env.SCREENSHOTS && POLICY.includes(view)) {
      await page.screenshot({ path: `${SHOTS}page-${view}-${test.info().project.name}.png`, fullPage: true });
    }
  }
  expect(Object.fromEntries(Object.entries(found).filter(([, v]) => v.length))).toEqual({});
});

test("axe finds nothing on an answer, a story and the page drawer", async ({ page }) => {
  await engineOff(page);
  await page.goto(`/?${new URLSearchParams({ q: seed.text, ...seed.filters })}`);
  await expect(page.getByRole("heading", { name: "Answer from the record" })).toBeVisible();
  await expect(page.getByText("Written by Claude, an AI model, from the pages cited.", { exact: false })).toBeVisible();
  const found: Record<string, string[]> = { answer: await violations(page) };
  await page.getByRole("button", { name: /^Open the scanned page behind citation/ }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  found.drawer = await violations(page);
  await page.keyboard.press("Escape");
  await page.goto("/");
  await page.getByRole("button", { name: `See the full answer: ${hero.question}` }).click();
  await expect(page.getByRole("region", { name: /^\d{4} and \d{4}$/ })).toBeVisible();
  found.story = await violations(page);
  expect(Object.fromEntries(Object.entries(found).filter(([, v]) => v.length))).toEqual({});
});

test("keyboard: skip link, menu, footer pages, a question, the drawer and the filters", async ({ page }) => {
  await engineOff(page);
  await page.goto("/");
  // Tab only once the page is loaded and the skip link is in place: a Tab pressed before then went to
  // the browser, not the page (the test failed now and then on CI).
  await page.waitForLoadState("load");
  await expect(page.locator(".skip-link")).toBeAttached();

  // The first Tab lands on the skip link, visibly, and it moves focus to the main content.
  await page.keyboard.press("Tab");
  await expect(page.locator(".skip-link")).toBeFocused();
  expect(await focusVisible(page)).toBe(true);
  await page.keyboard.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();

  // A story opens from its button with Enter.
  const storyButton = page.getByRole("button", { name: `See the full answer: ${hero.question}` });
  await storyButton.focus();
  expect(await focusVisible(page)).toBe(true);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("region", { name: /^\d{4} and \d{4}$/ })).toBeVisible();
  await page.goto("/");

  // Every footer page opens from the keyboard and moves focus to its heading.
  for (const [name, heading] of [
    ["Privacy", "Privacy"], ["Terms of use", "Terms of use"], ["Accessibility", "Accessibility"],
    ["Corrections and care", "Corrections and care"], ["About", "About"],
  ] as const) {
    const link = page.getByRole("navigation", { name: "About this site" }).getByRole("link", { name });
    await link.focus();
    expect(await focusVisible(page)).toBe(true);
    await page.keyboard.press("Enter");
    await expect(page.locator("#page-heading")).toHaveText(heading);
    await expect(page.locator("#page-heading")).toBeFocused();
  }

  // The scrollable data table on Privacy can be reached and scrolled from the keyboard.
  await page.getByRole("navigation", { name: "About this site" }).getByRole("link", { name: "Privacy" }).press("Enter");
  const table = page.getByRole("region", { name: "What happens to your data" });
  await table.focus();
  await expect(table).toBeFocused();

  // The menu's Ask returns to the question box with focus in it; a question is typed and sent.
  await page.getByRole("navigation", { name: "Pages" }).getByRole("button", { name: "Ask" }).press("Enter");
  await expect(page.locator("#question")).toBeFocused();
  await page.keyboard.type(seed.text);
  // The filters disclosure opens from the keyboard (Tab past Ask to the summary).
  await page.keyboard.press("Tab");
  await page.keyboard.press("Tab");
  await expect(page.locator("details.filters > summary")).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("details.filters")).toHaveAttribute("open", "");
  await page.locator("#question").focus();
  await page.keyboard.press("Escape");
  await page.locator("#question").fill("");
  await page.goto(`/?${new URLSearchParams({ q: seed.text, ...seed.filters })}`);
  await expect(page.getByRole("heading", { name: "Answer from the record" })).toBeVisible();

  // A citation mark opens the drawer; focus goes to Close, Tab stays inside, Escape returns focus.
  const mark = page.locator("article").getByRole("button", { name: /citation/i }).first();
  await mark.focus();
  expect(await focusVisible(page)).toBe(true);
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Close page drawer" })).toBeFocused();
  for (let i = 0; i < 8; i += 1) {
    await page.keyboard.press("Tab");
    expect(await dialog.evaluate((d) => d.contains(document.activeElement))).toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(mark).toBeFocused();
});
