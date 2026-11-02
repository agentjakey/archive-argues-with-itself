// Paced reveals: the parts of a reveal appear one after another at the given delays (milliseconds
// from the start). With less motion on, everything appears at once. A new key starts over.
import { useEffect, useState } from "react";

export const SOLO_PACE = [0, 800, 1600, 2400, 3200];
// The group split bar settles first (1.5 s), then the counts, the answer and the rest.
export const GROUP_PACE = [0, 1600, 2400, 3200, 4000];

export function useStaged(delays: number[], reduced: boolean, key: unknown, active = true): number {
  const [shown, setShown] = useState(reduced ? delays.length : 0);
  useEffect(() => {
    if (!active) {
      setShown(0);
      return;
    }
    if (reduced) {
      setShown(delays.length);
      return;
    }
    setShown(0);
    const timers = delays.map((ms, i) => window.setTimeout(() => setShown((n) => Math.max(n, i + 1)), ms));
    return () => timers.forEach((t) => window.clearTimeout(t));
    // The delays are constants; the key and the switches decide when to start over.
  }, [key, reduced, active]);
  if (!active) return 0;
  return reduced ? delays.length : shown;
}
