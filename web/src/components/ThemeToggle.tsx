import { useEffect, useState } from "react";
import { currentTheme, setTheme, THEME_EVENT, type Theme } from "../lib/theme";

/** The compact sun/moon control in the header. One press switches between light and dark; the
 *  button's name says what it will do, and the icon shows the theme it switches to. With no choice
 *  made the site follows the device setting. */
export function ThemeToggle() {
  const [theme, setLocal] = useState<Theme>(() => currentTheme());

  useEffect(() => {
    const sync = () => setLocal(currentTheme());
    const media = window.matchMedia?.("(prefers-color-scheme: light)");
    window.addEventListener(THEME_EVENT, sync);
    media?.addEventListener?.("change", sync);
    return () => {
      window.removeEventListener(THEME_EVENT, sync);
      media?.removeEventListener?.("change", sync);
    };
  }, []);

  const next: Theme = theme === "dark" ? "light" : "dark";
  const label = `Switch to ${next} theme`;
  return (
    <button
      type="button"
      className="icon-button"
      onClick={() => setLocal(setTheme(next))}
      aria-label={label}
      title={label}
      data-testid="theme-toggle"
    >
      {next === "light" ? <SunIcon /> : <MoonIcon />}
    </button>
  );
}

function SunIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <circle cx="12" cy="12" r="4.2" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <g stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
        <path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6" />
      </g>
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path
        d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  );
}
