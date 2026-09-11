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
  const s = p.toString();
  return s ? `?${s}` : "";
}

export function applyState(state: UrlState, mode: "push" | "replace"): void {
  const search = writeState(state);
  if (window.location.search === search) return;
  const url = `${window.location.pathname}${search}`;
  if (mode === "push") window.history.pushState({}, "", url);
  else window.history.replaceState({}, "", url);
}
