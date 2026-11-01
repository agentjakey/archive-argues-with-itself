// Catalogue browsing: static files only (summary.json and one file per decade), filtered in the
// browser. Archival text is shown as text, never as HTML. Nothing is stored in the browser.
const BASE = new URL("data/", document.baseURI);
const PAGE = 100;
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

let summary = null;
let current = [];
let shown = 0;
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

function render(reset) {
  const list = $("results");
  if (reset) {
    list.replaceChildren();
    shown = 0;
  }
  const next = current.slice(shown, shown + PAGE);
  for (const doc of next) list.appendChild(row(doc));
  shown += next.length;
  $("more").hidden = shown >= current.length;
  $("count").textContent = `${current.length.toLocaleString("en-CA")} documents match; showing ${shown.toLocaleString("en-CA")}.`;
}

async function update() {
  const key = $("decade").value;
  $("count").textContent = "Loading...";
  const docs = await loadDecade(key);
  current = docs.filter(matches);
  render(true);
}

async function main() {
  const res = await fetch(new URL("summary.json", BASE), { cache: "no-cache" });
  summary = await res.json();
  const keys = Object.keys(summary.decades).sort((a, b) => (a === "undated" ? 1 : b === "undated" ? -1 : a.localeCompare(b)));
  for (const k of keys) {
    const o = el("option", `${k === "undated" ? "Undated" : k} (${summary.decades[k].documents.toLocaleString("en-CA")})`);
    o.value = k;
    $("decade").appendChild(o);
  }
  $("decade").value = keys.includes("1980s") ? "1980s" : keys[0];
  for (const [p, n] of Object.entries(summary.places)) {
    const o = el("option", `${PLACE_NAMES[p] || p} (${n.toLocaleString("en-CA")})`);
    o.value = p;
    $("place").appendChild(o);
  }
  for (const [c, n] of Object.entries(summary.collections)) {
    const o = el("option", `${c} (${n.toLocaleString("en-CA")})`);
    o.value = c;
    $("collection").appendChild(o);
  }
  const cov = summary.coverage;
  $("totals").textContent = `${summary.documents.toLocaleString("en-CA")} documents known; ${(cov.indexed || 0).toLocaleString("en-CA")} indexed; ${(cov.text_fetched || 0).toLocaleString("en-CA")} with text fetched.`;
  $("method").textContent = summary.source.text;
  for (const id of ["decade", "place", "state", "collection"]) $(id).addEventListener("change", update);
  let timer = 0;
  $("text").addEventListener("input", () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(update, 250);
  });
  $("filters").addEventListener("submit", (e) => e.preventDefault());
  $("more").addEventListener("click", () => render(false));
  await update();
}

main().catch((e) => {
  $("totals").textContent = `The catalogue could not load (${e.message}).`;
});
