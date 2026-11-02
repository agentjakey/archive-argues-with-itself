// Kiosk mode and its anonymous daily totals.
//
// Two ways into kiosk presentation (the attract loop, the 60-second idle reset, the kiosk type scale):
//   - the kiosk's local server (exhibit/kiosk/serve.py) answers /exhibit/kiosk.json; that kiosk also
//     counts: the app posts one word per event (a mode started or finished, a choice made) and the
//     server adds it to that day's totals, and it prints the evidence card when it has a printer;
//   - online, /exhibit/?kiosk=1 (the short link /kiosk) turns on the same presentation with counting
//     and printing off. Nothing is stored in the browser either way.
// No visitor, session, time of day or answer text is ever sent.

export type KioskConfig = { kiosk: boolean; idle_reset_seconds: number; printer: boolean; counting: boolean };

const OFF: KioskConfig = { kiosk: false, idle_reset_seconds: 60, printer: false, counting: false };

/** Kiosk presentation asked for in the address (?kiosk=1), with counting and printing off. */
export function kioskFromUrl(search: string = typeof window === "undefined" ? "" : window.location.search): KioskConfig | null {
  return new URLSearchParams(search).get("kiosk") === "1" ? { kiosk: true, idle_reset_seconds: 60, printer: false, counting: false } : null;
}

export async function loadKiosk(): Promise<KioskConfig> {
  const fromUrl = kioskFromUrl();
  if (fromUrl) return fromUrl;
  try {
    const res = await fetch("./kiosk.json", { cache: "no-cache" });
    if (!res.ok) return OFF;
    const body = (await res.json()) as Partial<KioskConfig>;
    const kiosk = body.kiosk === true;
    return { kiosk, idle_reset_seconds: Number(body.idle_reset_seconds) || 60, printer: body.printer === true, counting: kiosk };
  } catch {
    return OFF;
  }
}

const EVENT = /^[a-z_]+(:[a-z_]+)?$/;

export function countEvent(config: KioskConfig, event: string): void {
  if (!config.kiosk || !config.counting || !EVENT.test(event)) return;
  void fetch("./count", { method: "POST", headers: { "content-type": "text/plain" }, body: event }).catch(() => undefined);
}
