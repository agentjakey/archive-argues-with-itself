// Cloudflare Turnstile in invisible mode: a fresh single-use token for each request that may wake
// the engine or call the model. The script loads only when the first token is needed. Without a
// site key (local development) no token is requested and none is sent.
import { TURNSTILE_SITEKEY } from "./config";

interface TurnstileApi {
  render(element: HTMLElement, options: Record<string, unknown>): string;
  execute(widgetId: string): void;
  reset(widgetId: string): void;
}

declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

const SCRIPT = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
const TOKEN_TIMEOUT_MS = 15_000;

let scriptLoading: Promise<void> | null = null;
let widgetId: string | null = null;
let waiting: ((token: string | null) => void) | null = null;
let queue: Promise<unknown> = Promise.resolve();

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

function settle(token: string | null): void {
  const done = waiting;
  waiting = null;
  done?.(token);
}

function ensureWidget(api: TurnstileApi): string {
  if (widgetId) return widgetId;
  const holder = document.createElement("div");
  holder.setAttribute("aria-hidden", "true");
  holder.style.position = "fixed";
  holder.style.bottom = "0";
  holder.style.right = "0";
  document.body.appendChild(holder);
  widgetId = api.render(holder, {
    sitekey: TURNSTILE_SITEKEY,
    execution: "execute",
    callback: (token: string) => settle(token),
    "error-callback": () => settle(null),
    "timeout-callback": () => settle(null),
  });
  return widgetId;
}

async function oneToken(): Promise<string | null> {
  await loadScript();
  const api = window.turnstile;
  if (!api) return null;
  const id = ensureWidget(api);
  const token = new Promise<string | null>((resolve) => {
    waiting = resolve;
    window.setTimeout(() => settle(null), TOKEN_TIMEOUT_MS);
  });
  api.execute(id);
  const result = await token;
  api.reset(id);
  return result;
}

/** A fresh Turnstile token, or null when Turnstile is not configured or could not run. Requests are
 *  serialized: the widget produces one token at a time. */
export function turnstileToken(): Promise<string | null> {
  if (!TURNSTILE_SITEKEY) return Promise.resolve(null);
  const next = queue.then(oneToken, oneToken).catch(() => null);
  queue = next;
  return next;
}
