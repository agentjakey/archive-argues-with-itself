import type { View } from "../lib/urlstate";
import type { ScopeInfo } from "../types";
import { KioskQr } from "./KioskQr";
import { ScopeSwitcher } from "./ScopeSwitcher";

interface Props {
  kiosk: boolean;
  view: View | null;
  onView: (view: View | null) => void;
  scopes?: ScopeInfo[] | null;      // more than one -> the switcher renders; null/one -> hidden
  activeScope?: string;
  activeScopeInfo?: ScopeInfo | null;   // the active scope's facts, for the subtitle and the corpus strip
  onSwitchScope?: (name: string) => void;
}

const LINKS: { view: View; label: string }[] = [
  { view: "explore", label: "Explore" },
  { view: "how", label: "How this works" },
  { view: "gaps", label: "Gaps" },
  { view: "map", label: "Coverage map" },
  { view: "timeline", label: "Timeline" },
  { view: "sources", label: "Sources" },
  { view: "about", label: "About" },
];

// A lighter, secondary nav: muted by default so it never competes with the hero's primary
// action; the active page reads in ink, and any link inks in on hover.
const navCls = (active: boolean) =>
  `bg-transparent border-0 p-0 cursor-pointer font-sans text-sm underline-offset-2 hover:underline ${
    active ? "text-ink underline" : "text-muted hover:text-ink"
  }`;

export function Header({ kiosk, view, onView, scopes, activeScope, activeScopeInfo, onSwitchScope }: Props) {
  const cw = activeScopeInfo?.coverage_window;
  return (
    <header className="mb-6">
      <div className="flex items-start justify-between gap-6">
        <div>
          <h1 className="font-serif text-3xl leading-tight">
            <button type="button" className="linkish no-underline font-serif text-3xl" onClick={() => onView(null)}>
              Archive Argues With Itself
            </button>
          </h1>
          <p className="mt-2 max-w-prose text-muted">
            An evidence trail with page-level provenance over Canadian government public-health
            publications. Not a chatbot.
          </p>
          {activeScopeInfo && cw && cw.min_year != null && cw.max_year != null && (
            <p className="mt-1 max-w-prose text-sm text-muted">
              {activeScopeInfo.label}, {cw.min_year} to {cw.max_year}
            </p>
          )}
        </div>
        {kiosk && <KioskQr />}
      </div>
      <nav
        className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-rule pt-2"
        aria-label="Pages"
      >
        <button type="button" className={navCls(view === null)} aria-current={view === null ? "page" : undefined} onClick={() => onView(null)}>
          Ask
        </button>
        {LINKS.map((l) => (
          <button
            key={l.view}
            type="button"
            className={navCls(view === l.view)}
            aria-current={view === l.view ? "page" : undefined}
            onClick={() => onView(l.view)}
          >
            {l.label}
          </button>
        ))}
      </nav>
      {scopes && onSwitchScope && (
        <ScopeSwitcher scopes={scopes} active={activeScope ?? ""} onSwitch={onSwitchScope} />
      )}
    </header>
  );
}
