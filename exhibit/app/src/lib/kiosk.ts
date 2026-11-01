// Kiosk mode and its anonymous daily totals.
//
// The kiosk's local server (exhibit/kiosk/serve.py) answers /exhibit/kiosk.json; the online exhibit
// has no such file, so online the app never counts anything. On the kiosk, the app posts one word
// per event (a mode started or finished, a choice made) and the server adds it to that day's totals.
// No visitor, session, time of day or answer text is ever sent.

export type KioskConfig = { kiosk: boolean; idle_reset_seconds: number; printer: boolean };

const OFF: KioskConfig = { kiosk: false, idle_reset_seconds: 60, printer: false };

export async function loadKiosk(): Promise<KioskConfig> {
  try {
    const res = await fetch("./kiosk.json", { cache: "no-cache" });
    if (!res.ok) return OFF;
    const body = (await res.json()) as Partial<KioskConfig>;
    return { kiosk: body.kiosk === true, idle_reset_seconds: Number(body.idle_reset_seconds) || 60, printer: body.printer === true };
  } catch {
    return OFF;
  }
}

const EVENT = /^[a-z_]+(:[a-z_]+)?$/;

export function countEvent(config: KioskConfig, event: string): void {
  if (!config.kiosk || !EVENT.test(event)) return;
  void fetch("./count", { method: "POST", headers: { "content-type": "text/plain" }, body: event }).catch(() => undefined);
}
