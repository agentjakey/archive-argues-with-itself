// Every round fits its screen: at 1280x720, 1366x768, 1440x900, 1920x1080, 3840x2160 and 390x844, in
// the normal web view and in kiosk mode (?kiosk=1), the page is never wider than the viewport, no text
// or control is clipped or pushed off screen, and in kiosk mode a round also fits with no vertical
// scroll. Each screen of a visit is checked before and after its answer. With SHOTS=<folder> a
// screenshot of every checked screen is written there (one folder per mode and size).
import { expect, test, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

const SIZES: [number, number][] = [
  [1280, 720],
  [1366, 768],
  [1440, 900],
  [1920, 1080],
  [3840, 2160],
  [390, 844],
];
const MODES = [
  { name: "web", path: "/exhibit/" },
  { name: "kiosk", path: "/exhibit/?kiosk=1" },
] as const;
const SHOTS = process.env.SHOTS ?? "";

type Problem = { what: string; where: string };

/** What does not fit on the screen as it stands. */
async function problems(page: Page, kiosk: boolean): Promise<Problem[]> {
  return page.evaluate((kioskMode) => {
    const out: { what: string; where: string }[] = [];
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const doc = document.documentElement;
    const name = (el: Element) => {
      const text = (el.textContent ?? "").trim().replace(/\s+/g, " ").slice(0, 40);
      return `${el.tagName.toLowerCase()}.${(el.getAttribute("class") ?? "").split(" ").join(".")} "${text}"`;
    };
    if (doc.scrollWidth > vw + 1) out.push({ what: `page ${doc.scrollWidth}px wide in a ${vw}px viewport`, where: "document" });
    if (kioskMode && doc.scrollHeight > vh + 1) out.push({ what: `page ${doc.scrollHeight}px tall in a ${vh}px viewport`, where: "document" });
    for (const el of Array.from(document.querySelectorAll("body *"))) {
      if (el.closest(".sr-only, [data-allow-clip], svg")) continue;
      const style = getComputedStyle(el);
      if (style.display === "none" || style.visibility === "hidden") continue;
      const rect = el.getBoundingClientRect();
      if (rect.width <= 1 && rect.height <= 1) continue; // visually hidden text (a screen reader still reads it)
      if (rect.width === 0 || rect.height === 0) continue;
      const box = el as HTMLElement;
      // Text or controls cut off by a box that hides its overflow (an intended scroll area is fine).
      const hidesX = style.overflowX === "hidden" || style.overflowX === "clip";
      const hidesY = style.overflowY === "hidden" || style.overflowY === "clip";
      if (hidesX && box.scrollWidth > box.clientWidth + 1) out.push({ what: "clipped across", where: name(el) });
      if (hidesY && box.scrollHeight > box.clientHeight + 1 && style.webkitLineClamp === "none")
        out.push({ what: "clipped down", where: name(el) });
      // A control pushed past the edge of the screen.
      if (el.matches("button, a, input, select, [role=radio], [role=button]")) {
        if (rect.left < -1 || rect.right > vw + 1) out.push({ what: `control off screen (${Math.round(rect.left)}..${Math.round(rect.right)})`, where: name(el) });
        // In kiosk mode a control must be on the screen, or inside a panel that scrolls to it
        // (a reveal or a page's text): that panel is reachable, not clipped.
        let scroller: Element | null = el.parentElement;
        while (scroller && !["auto", "scroll"].includes(getComputedStyle(scroller).overflowY)) scroller = scroller.parentElement;
        if (kioskMode && !scroller && (rect.top < -1 || rect.bottom > vh + 1)) out.push({ what: "control below the screen", where: name(el) });
      }
    }
    return out;
  }, kiosk);
}

async function check(page: Page, mode: string, size: string, screen: string) {
  if (SHOTS) {
    const dir = join(SHOTS, mode, size);
    mkdirSync(dir, { recursive: true });
    await page.screenshot({ path: join(dir, `${screen}.png`) });
  }
  const found = await problems(page, mode === "kiosk");
  expect.soft(found, `${mode} ${size} ${screen}`).toEqual([]);
}

/** Answers whatever round is on screen: a pick for Same or Not?, the main button otherwise. */
async function answer(page: Page) {
  const choice = page.locator(".choice").first();
  if (await choice.isVisible().catch(() => false)) {
    await choice.click();
    return;
  }
  await page.locator("[data-primary]").first().click();
}

for (const mode of MODES) {
  for (const [w, h] of SIZES) {
    test(`${mode.name} ${w}x${h}: every round fits`, async ({ page }) => {
      const size = `${w}x${h}`;
      await page.setViewportSize({ width: w, height: h });
      await page.emulateMedia({ reducedMotion: "reduce" });
      await page.goto(mode.path);
      await expect(page.getByRole("button", { name: "Touch to start" })).toBeVisible();
      await check(page, mode.name, size, "00-attract");
      await page.getByRole("button", { name: "Touch to start" }).click();
      for (let i = 1; i <= 8; i++) {
        const stepEl = page.locator("[data-step]").first();
        if (!(await stepEl.isVisible().catch(() => false))) break;
        const kind = (await stepEl.getAttribute("data-step")) ?? "round";
        await check(page, mode.name, size, `${String(i).padStart(2, "0")}-${kind}-ask`);
        await answer(page);
        await page.waitForTimeout(150);
        await check(page, mode.name, size, `${String(i).padStart(2, "0")}-${kind}-reveal`);
        const next = page.locator("[data-primary]").first();
        if (!(await next.isVisible().catch(() => false))) break;
        await next.click();
      }
      await check(page, mode.name, size, "99-chronicle");
    });
  }
}
