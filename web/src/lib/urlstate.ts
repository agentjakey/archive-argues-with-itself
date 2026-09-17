import type { Filters } from "../types";

// The URL is the app's state: q + filters on ask, pins=a,b on pin, kiosk preserved,
// view=how|gaps|about for the reading pages.

export type View = "how" | "gaps" | "about";
export const VIEWS: readonly View[] = ["how", "gaps", "about"];

export interface UrlState {
  q: string;
  filters: Filters;
  pins: string[];
  kiosk: boolean;
  offline?: boolean;
  view?: View;
  story?: string;   // a curated story comparison, so its permalink reproduces it
  scope?: string;   // the active corpus; absent means the pilot default (byte-identical URL)
}

const FILTER_KEYS = ["period", "jurisdiction", "doc_type"] as const;

export function readState(search: string): UrlState {
  const p = new URLSearchParams(search);
  const filters: Filters = {};
  for (const k of FILTER_KEYS) {
    const v = p.get(k);
    if (v) (filters as Record<string, string>)[k] = v;
  }
  const pins = (p.get("pins") ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, 2);
  const view = p.get("view");
  const state: UrlState = { q: (p.get("q") ?? "").trim(), filters, pins, kiosk: p.get("kiosk") === "1" };
  if (p.get("offline") === "1") state.offline = true;
  if (view && (VIEWS as readonly string[]).includes(view)) state.view = view as View;
  const story = (p.get("story") ?? "").trim();
  if (story) state.story = story;
  const scope = (p.get("scope") ?? "").trim();
  if (scope) state.scope = scope;
  return state;
}

export function writeState(state: UrlState): string {
  const p = new URLSearchParams();
  if (state.q) p.set("q", state.q);
  for (const k of FILTER_KEYS) {
    const v = (state.filters as Record<string, string | undefined>)[k];
    if (v) p.set(k, v);
  }
  if (state.pins.length) p.set("pins", state.pins.join(","));
  if (state.kiosk) p.set("kiosk", "1");
  if (state.offline) p.set("offline", "1");
  if (state.view) p.set("view", state.view);
  if (state.story) p.set("story", state.story);
  if (state.scope) p.set("scope", state.scope);
  const s = p.toString();
  return s ? `?${s}` : "";
}

export function applyState(state: UrlState, mode: "push" | "replace"): void {
  let search = writeState(state);
  // Preserve the active scope across every client-side navigation. The switcher sets it via
  // a full reload, so callers never need to thread it through; carry it here unless the state
  // already names one. Without this, an ask/pin/view would drop ?scope and silently fall back
  // to the pilot, mixing corpora.
  if (!state.scope) {
    const scope = new URLSearchParams(window.location.search).get("scope");
    if (scope) {
      const inner = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
      inner.set("scope", scope);
      const s = inner.toString();
      search = s ? `?${s}` : "";
    }
  }
  if (window.location.search === search) return;
  const url = `${window.location.pathname}${search}`;
  if (mode === "push") window.history.pushState({}, "", url);
  else window.history.replaceState({}, "", url);
}
