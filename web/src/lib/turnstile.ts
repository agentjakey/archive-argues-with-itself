// Cloudflare Turnstile: a fresh single-use token for each request that may wake the engine or call
// the model. The widget renders into the visible slot beside Ask (#turnstile-slot) with appearance
// "interaction-only", so it works the same whichever widget mode the site key is set to: in
// Invisible mode nothing is ever shown; in Managed mode most visitors see nothing, and a visitor
// Cloudflare wants to check sees the challenge right next to the button they pressed. The script
// loads only when the first token is needed. Without a site key (local development) no token is
// requested and none is sent.
import { TURNSTILE_SITEKEY } from "./config";

interface TurnstileApi {
  render(element: HTMLElement, options: Record<string, unknown>): string;
  execute(widgetId: string): void;
  reset(widgetId: string): void;
  remove(widgetId: string): void;
}

declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

export const SLOT_ID = "turnstile-slot";
const SCRIPT = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
const TOKEN_TIMEOUT_MS = 20_000;            // no challenge shown: a token normally comes in a second or two
const INTERACTIVE_TIMEOUT_MS = 180_000;     // a challenge is on screen: give the visitor time to answer it

/** Why no token came back. */
export type TokenFailure = "failed" | "expired" | "timeout" | "unavailable";

export interface TokenResult {
  token: string | null;
  failure: TokenFailure | null;
}

/** What the slot beside Ask should say: nothing, or that a check is waiting for the visitor. */
export type ChallengeState = "idle" | "interactive";

let scriptLoading: Promise<void> | null = null;
let widgetId: string | null = null;
let widgetHolder: HTMLElement | null = null;
let waiting: ((result: TokenResult) => void) | null = null;
let deadline: number | null = null;
let queue: Promise<unknown> = Promise.resolve();
const listeners = new Set<(state: ChallengeState) => void>();

/** Follow whether an interactive check is on screen (the slot's hint uses it). */
export function onChallengeState(listener: (state: ChallengeState) => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function announce(state: ChallengeState): void {
  listeners.forEach((l) => l(state));
}

function loadScript(): Promise<void> {
  if (window.turnstile) return Promise.resolve();
  if (!scriptLoading) {
    scriptLoading = new Promise<void>((resolve, reject) => {
      const tag = document.createElement("script");
      tag.src = SCRIPT;
      tag.async = true;
      tag.onload = () => resolve();
      tag.onerror = () => {
        scriptLoading = null;
        reject(new Error("turnstile script did not load"));
      };
      document.head.appendChild(tag);
    });
  }
  return scriptLoading;
}

function settle(result: TokenResult): void {
  const done = waiting;
  waiting = null;
  if (deadline !== null) window.clearTimeout(deadline);
  deadline = null;
  announce("idle");
  done?.(result);
}

function arm(ms: number): void {
  if (deadline !== null) window.clearTimeout(deadline);
  deadline = window.setTimeout(() => settle({ token: null, failure: "timeout" }), ms);
}

/** The element the widget lives in: the slot beside Ask when the page shows one, else a holder at
 *  the end of the page (a question asked from a page without the ask box). Never hidden from
 *  assistive technology: in Managed mode it can hold a challenge the visitor must answer. */
function slot(): HTMLElement {
  const own = document.getElementById(SLOT_ID);
  if (own) return own;
  const holder = document.createElement("div");
  holder.className = "turnstile-fallback";
  document.body.appendChild(holder);
  return holder;
}

function ensureWidget(api: TurnstileApi): string {
  const target = slot();
  // The slot is re-created when the visitor moves between pages; a widget left in a detached
  // element is removed and drawn again in the current one.
  if (widgetId && widgetHolder && widgetHolder.isConnected && widgetHolder === target.firstElementChild) return widgetId;
  if (widgetId) {
    try {
      api.remove(widgetId);
    } catch {
      // already gone with its element
    }
    widgetId = null;
  }
  widgetHolder = document.createElement("div");
  target.replaceChildren(widgetHolder);
  widgetId = api.render(widgetHolder, {
    sitekey: TURNSTILE_SITEKEY,
    appearance: "interaction-only",
    execution: "execute",
    action: "ask",
    retry: "never",                    // a failure is shown with our own retry, not retried silently
    "refresh-expired": "manual",
    "refresh-timeout": "manual",
    callback: (token: string) => settle({ token, failure: null }),
    "error-callback": () => {
      settle({ token: null, failure: "failed" });
      return true;                     // handled here: no console error from the widget
    },
    "expired-callback": () => settle({ token: null, failure: "expired" }),
    "timeout-callback": () => settle({ token: null, failure: "timeout" }),
    "before-interactive-callback": () => {
      arm(INTERACTIVE_TIMEOUT_MS);
      announce("interactive");
    },
    "after-interactive-callback": () => announce("idle"),
  });
  return widgetId;
}

async function oneToken(): Promise<TokenResult> {
  try {
    await loadScript();
  } catch {
    return { token: null, failure: "unavailable" };
  }
  const api = window.turnstile;
  if (!api) return { token: null, failure: "unavailable" };
  let id: string;
  try {
    id = ensureWidget(api);
  } catch {
    return { token: null, failure: "unavailable" };
  }
  const result = new Promise<TokenResult>((resolve) => {
    waiting = resolve;
  });
  arm(TOKEN_TIMEOUT_MS);
  try {
    api.execute(id);
  } catch {
    settle({ token: null, failure: "failed" });
  }
  const out = await result;
  try {
    api.reset(id);                     // tokens are single use; the next request runs a fresh check
  } catch {
    // a widget whose element went away is drawn again next time
  }
  return out;
}

/** A fresh Turnstile token, with the reason when there is none. Not configured (local development):
 *  no token and no failure. Requests are serialized: the widget produces one token at a time. */
export function turnstileResult(): Promise<TokenResult> {
  if (!TURNSTILE_SITEKEY) return Promise.resolve({ token: null, failure: null });
  const next = queue.then(oneToken, oneToken).catch(() => ({ token: null, failure: "unavailable" as const }));
  queue = next;
  return next;
}

/** The token alone, or null. */
export async function turnstileToken(): Promise<string | null> {
  return (await turnstileResult()).token;
}

/** For tests: forget the widget and the script state. */
export function resetTurnstileForTests(): void {
  scriptLoading = null;
  widgetId = null;
  widgetHolder = null;
  waiting = null;
  if (deadline !== null) window.clearTimeout(deadline);
  deadline = null;
  queue = Promise.resolve();
  listeners.clear();
}
