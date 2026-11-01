// Reset after a quiet minute. Any touch, click, key or wheel counts as activity. A short warning
// shows for the last ten seconds so a visitor who is reading can keep going.
import { useEffect, useRef, useState } from "react";

const ACTIVITY = ["pointerdown", "keydown", "wheel", "touchstart"] as const;

export function useIdleReset(seconds: number, onReset: () => void, active: boolean): boolean {
  const [warning, setWarning] = useState(false);
  const last = useRef(Date.now());
  const reset = useRef(onReset);
  reset.current = onReset;
  useEffect(() => {
    if (!active) {
      setWarning(false);
      return;
    }
    last.current = Date.now();
    const bump = () => {
      last.current = Date.now();
      setWarning(false);
    };
    ACTIVITY.forEach((name) => window.addEventListener(name, bump, { passive: true }));
    const timer = window.setInterval(() => {
      const quiet = (Date.now() - last.current) / 1000;
      if (quiet >= seconds) {
        last.current = Date.now();
        setWarning(false);
        reset.current();
      } else {
        setWarning(quiet >= seconds - 10);
      }
    }, 1000);
    return () => {
      ACTIVITY.forEach((name) => window.removeEventListener(name, bump));
      window.clearInterval(timer);
    };
  }, [seconds, active]);
  return warning;
}
