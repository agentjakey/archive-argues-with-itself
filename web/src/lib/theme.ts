// The light and dark themes. design/theme-boot.js (loaded before the app) sets html[data-theme] and
// owns the one storage key; this module reads the current theme and asks it to change. Without the
// boot script (unit tests, a bare dev page) it falls back to the same rules.

export type Theme = "light" | "dark";

interface BootApi {
  apply: () => Theme;
  set: (theme: Theme) => Theme;
  kiosk: boolean;
}

function boot(): BootApi | null {
  return ((window as unknown as { archiveTheme?: BootApi }).archiveTheme ?? null);
}

export function currentTheme(): Theme {
  const attr = document.documentElement.getAttribute("data-theme");
  if (attr === "light" || attr === "dark") return attr;
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

export const THEME_EVENT = "archive-theme";

export function setTheme(theme: Theme): Theme {
  const api = boot();
  let applied: Theme = theme;
  if (api) {
    applied = api.set(theme);
  } else {
    document.documentElement.setAttribute("data-theme", theme);
  }
  window.dispatchEvent(new CustomEvent(THEME_EVENT, { detail: applied }));
  return applied;
}
