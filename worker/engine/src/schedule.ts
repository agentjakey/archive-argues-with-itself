// Keep-warm windows (off by default): KEEP_WARM_WINDOWS lists UTC windows during which the cron
// wakes the engine, for example an exhibit's opening hours. Format: windows separated by ";",
// each "<days> HH:MM-HH:MM" where days is a day ("tue"), a range ("mon-fri") or a list
// ("sat,sun"). An empty value turns keep-warm off.

const DAYS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];

export interface Window {
  days: Set<number>;
  startMinute: number;
  endMinute: number;
}

function minuteOf(text: string): number {
  const match = /^(\d{1,2}):(\d{2})$/.exec(text.trim());
  if (!match) throw new Error(`not a time: ${text}`);
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  if (hours > 24 || minutes > 59 || (hours === 24 && minutes > 0)) throw new Error(`not a time: ${text}`);
  return hours * 60 + minutes;
}

function daysOf(text: string): Set<number> {
  const out = new Set<number>();
  for (const part of text.toLowerCase().split(",")) {
    const [first, last] = part.trim().split("-");
    const a = DAYS.indexOf(first);
    const b = last === undefined ? a : DAYS.indexOf(last);
    if (a < 0 || b < 0) throw new Error(`not a day: ${part}`);
    for (let d = a; ; d = (d + 1) % 7) {
      out.add(d);
      if (d === b) break;
    }
  }
  return out;
}

export function parseWindows(spec: string): Window[] {
  return spec
    .split(";")
    .map((w) => w.trim())
    .filter(Boolean)
    .map((w) => {
      const [days, hours] = w.split(/\s+/);
      if (!hours) throw new Error(`a window needs days and hours: ${w}`);
      const [start, end] = hours.split("-");
      return { days: daysOf(days), startMinute: minuteOf(start), endMinute: minuteOf(end) };
    });
}

/** True when now (UTC) falls inside one of the windows. A malformed spec keeps the engine cold. */
export function keepWarmNow(spec: string | undefined, now: Date): boolean {
  if (!spec || !spec.trim()) return false;
  let windows: Window[];
  try {
    windows = parseWindows(spec);
  } catch {
    return false;
  }
  const day = now.getUTCDay();
  const minute = now.getUTCHours() * 60 + now.getUTCMinutes();
  return windows.some((w) => w.days.has(day) && minute >= w.startMinute && minute < w.endMinute);
}
