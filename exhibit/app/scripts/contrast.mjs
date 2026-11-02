// Measures the WCAG contrast ratio of every text and control colour pair the kiosk uses, from the
// colour tokens in src/styles.css, and fails when a pair is under its bar: 7:1 for body text (AAA),
// 4.5:1 for large text (AAA large), 3:1 for control edges and graphics (WCAG 1.4.11).
//   node scripts/contrast.mjs
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
const root = css.slice(css.indexOf(":root {"), css.indexOf("}", css.indexOf(":root {")));
const tokens = Object.fromEntries([...root.matchAll(/--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})/g)].map((m) => [m[1], m[2]]));

function luminance(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const lin = (c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}
function ratio(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

// [foreground, background, bar, where it is used]
const PAIRS = [
  ["text", "bg", 7, "body text, headings, page text"],
  ["text", "surface", 7, "claims, choices, page panels"],
  ["text", "surface-2", 7, "pressed toggles, dial buttons"],
  ["muted", "bg", 7, "secondary text, notes, review status"],
  ["muted", "surface", 7, "choice help, card notes on panels"],
  ["muted", "surface-2", 7, "secondary text on raised panels"],
  ["gold", "bg", 7, "kickers, verdicts, dial year, split answer"],
  ["gold", "surface", 7, "panel labels, checklist marks"],
  ["ink", "gold", 7, "main buttons, marked quotes"],
  ["ink", "text", 7, "the evidence card"],
  ["gold", "surface-2", 4.5, "large text only"],
  ["line", "bg", 3, "control edges"],
  ["line", "surface", 3, "control edges on panels"],
  ["ink", "muted", 3, "split-bar shapes (graphics)"],
  ["ink", "line", 3, "split-bar shapes (graphics)"],
];

let failed = 0;
for (const [fg, bg, bar, where] of PAIRS) {
  const r = ratio(tokens[fg], tokens[bg]);
  const ok = r >= bar;
  if (!ok) failed += 1;
  console.log(`${ok ? "ok  " : "FAIL"} ${fg} ${tokens[fg]} on ${bg} ${tokens[bg]}: ${r.toFixed(2)}:1 (bar ${bar}:1) ${where}`);
}
process.exit(failed ? 1 : 0);
