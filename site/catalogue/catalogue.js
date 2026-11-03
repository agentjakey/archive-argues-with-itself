// Catalogue browsing: static files only (summary.json and one file per decade), filtered in the
// browser. Archival text is shown as text, never as HTML. The search and filters live in the URL
// (?q=, &decade=, &place=, &state=, &collection=), so a search can be shared or bookmarked; the only
// thing kept in the browser is the visitor's own light or dark choice, by /theme-boot.js.
const BASE = new URL("data/", document.baseURI);
const PAGE = 100;
const ALL = "all";
const STATE_NAMES = { known: "Known", text_fetched: "Text fetched", indexed: "Indexed" };
const PLACE_NAMES = {
  federal: "Federal", ontario: "Ontario", alberta: "Alberta", quebec: "Quebec", british_columbia: "British Columbia",
  manitoba: "Manitoba", saskatchewan: "Saskatchewan", nova_scotia: "Nova Scotia", new_brunswick: "New Brunswick",
  newfoundland: "Newfoundland and Labrador", prince_edward_island: "Prince Edward Island", yukon: "Yukon",
  northwest_territories: "Northwest Territories", nunavut: "Nunavut", international: "International", unknown: "Place unknown",
};

const $ = (id) => document.getElementById(id);
const el = (tag, text, cls) => {
  const e = document.createElement(tag);
  if (text !== undefined && text !== null) e.textContent = text;
  if (cls) e.className = cls;
  return e;
};
const fmt = (n) => n.toLocaleString("en-CA");

let summary = null;
let keys = [];
let current = [];
let shown = 0;
let run = 0;
const cache = new Map();

function topState(states) {
  if (states.some((s) => s.startsWith("indexed"))) return "indexed";
  if (states.includes("text_fetched")) return "text_fetched";
  return "known";
}

async function loadDecade(key) {
  if (!cache.has(key)) {
    const res = await fetch(new URL(`decades/${key}.json`, BASE));
    if (!res.ok) throw new Error(`decade ${key}: ${res.status}`);
    cache.set(key, await res.json());
  }
  return cache.get(key);
}

function matches(doc) {
  const place = $("place").value;
  const state = $("state").value;
  const coll = $("collection").value;
  const text = $("text").value.trim().toLowerCase();
  if (place && doc.p !== place) return false;
  if (state && topState(doc.s) !== state) return false;
  if (coll && !doc.c.includes(coll)) return false;
  if (text && !(`${doc.t} ${doc.i || ""}`.toLowerCase().includes(text))) return false;
  return true;
}

function row(doc) {
  const li = el("li", null, "doc");
  const a = el("a", doc.t || doc.id);
  a.href = `https://archive.org/details/${encodeURIComponent(doc.id)}`;
  a.rel = "noreferrer";
  li.appendChild(a);
  const meta = el("p", null, "meta");
  const date = doc.y !== null ? `${doc.y}` : doc.d ? `undated in the catalogue; ${doc.d.year} read from the title` : "undated";
  meta.appendChild(el("span", date));
  meta.appendChild(el("span", PLACE_NAMES[doc.p] || doc.p));
  if (doc.i) meta.appendChild(el("span", doc.i));
  li.appendChild(meta);
  const badges = el("p", null, "badges");
  const top = topState(doc.s);
  badges.appendChild(el("span", STATE_NAMES[top], `badge ${top}`));
  for (const s of doc.s.filter((x) => x.startsWith("indexed:"))) badges.appendChild(el("span", `in ${s.split(":")[1]}`, "scope"));
  li.appendChild(badges);
  return li;
}

function countLine(done, total) {
  const searching = total > 1 && done < total ? ` Searching decade ${done} of ${total}...` : "";
  return `${fmt(current.length)} documents match; showing ${fmt(shown)}.${searching}`;
}

function render(reset, done = 1, total = 1) {
  const list = $("results");
  if (reset) {
    list.replaceChildren();
    shown = 0;
  }
  const next = current.slice(shown, shown + PAGE);
  for (const doc of next) list.appendChild(row(doc));
  shown += next.length;
  $("more").hidden = shown >= current.length;
  $("count").textContent = countLine(done, total);
}

function writeUrl() {
  const p = new URLSearchParams();
  const text = $("text").value.trim();
  if (text) p.set("q", text);
  p.set("decade", $("decade").value);
  for (const id of ["place", "state", "collection"]) if ($(id).value) p.set(id, $(id).value);
  const qs = p.toString();
  window.history.replaceState(null, "", `${window.location.pathname}${qs ? `?${qs}` : ""}`);
}

async function update() {
  const mine = ++run;
  writeUrl();
  const key = $("decade").value;
  const wanted = key === ALL ? keys : [key];
  current = [];
  render(true, 0, wanted.length);
  $("count").textContent = "Loading...";
  for (let i = 0; i < wanted.length; i++) {
    const docs = await loadDecade(wanted[i]);
    if (mine !== run) return;   // a newer search replaced this one
    const found = docs.filter(matches);
    current = current.concat(found);
    if (shown < PAGE) render(false, i + 1, wanted.length);
    else {
      $("more").hidden = shown >= current.length;
      $("count").textContent = countLine(i + 1, wanted.length);
    }
  }
}

function themeToggle() {
  const api = window.archiveTheme;
  const button = $("theme-toggle");
  if (!api || !button || api.kiosk) return;
  const sun = '<svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="4.2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>';
  const moon = '<svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>';
  const paint = () => {
    const next = document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light";
    const label = `Switch to ${next} theme`;
    button.innerHTML = next === "light" ? sun : moon;
    button.setAttribute("aria-label", label);
    button.title = label;
  };
  button.hidden = false;
  paint();
  button.addEventListener("click", () => {
    const next = document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light";
    api.set(next);
    paint();
  });
  window.matchMedia?.("(prefers-color-scheme: light)").addEventListener?.("change", paint);
}

async function main() {
  themeToggle();
  const res = await fetch(new URL("summary.json", BASE), { cache: "no-cache" });
  summary = await res.json();
  keys = Object.keys(summary.decades).sort((a, b) => (a === "undated" ? 1 : b === "undated" ? -1 : a.localeCompare(b)));
  const all = el("option", `All decades (${fmt(summary.documents)}; a larger download)`);
  all.value = ALL;
  $("decade").appendChild(all);
  for (const k of keys) {
    const o = el("option", `${k === "undated" ? "Undated" : k} (${fmt(summary.decades[k].documents)})`);
    o.value = k;
    $("decade").appendChild(o);
  }
  for (const [p, n] of Object.entries(summary.places)) {
    const o = el("option", `${PLACE_NAMES[p] || p} (${fmt(n)})`);
    o.value = p;
    $("place").appendChild(o);
  }
  for (const [c, n] of Object.entries(summary.collections)) {
    const o = el("option", `${c} (${fmt(n)})`);
    o.value = c;
    $("collection").appendChild(o);
  }

  // Restore a search from the URL. A title search with no decade looks in every decade, so the
  // search box on the home page can hand its words straight to this page.
  const params = new URLSearchParams(window.location.search);
  const q = (params.get("q") || "").slice(0, 200);
  $("text").value = q;
  const decade = params.get("decade");
  $("decade").value = decade && (decade === ALL || keys.includes(decade)) ? decade : q ? ALL : keys.includes("1980s") ? "1980s" : keys[0];
  for (const id of ["place", "state", "collection"]) {
    const v = params.get(id);
    if (v && [...$(id).options].some((o) => o.value === v)) $(id).value = v;
  }

  const cov = summary.coverage;
  $("totals").textContent = `${fmt(summary.documents)} documents known; ${fmt(cov.indexed || 0)} indexed; ${fmt(cov.text_fetched || 0)} with text fetched.`;
  $("method").textContent = summary.source.text;
  for (const id of ["decade", "place", "state", "collection"]) $(id).addEventListener("change", update);
  let timer = 0;
  $("text").addEventListener("input", () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(update, 300);
  });
  $("filters").addEventListener("submit", (e) => {
    e.preventDefault();
    window.clearTimeout(timer);
    update();
  });
  $("more").addEventListener("click", () => render(false, 1, 1));
  await update();
}

main().catch((e) => {
  $("totals").textContent = `The catalogue could not load (${e.message}).`;
});
