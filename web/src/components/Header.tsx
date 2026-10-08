import type { View } from "../lib/urlstate";
import type { ScopeInfo } from "../types";
import { KioskQr } from "./KioskQr";
import { ScopeSwitcher } from "./ScopeSwitcher";

interface Props {
  kiosk: boolean;
  view: View | null;
  onView: (view: View | null) => void;
  onAsk?: () => void;               // nav "Ask": return to the landing AND focus the ask input
  scopes?: ScopeInfo[] | null;      // more than one -> the switcher renders; null/one -> hidden
  activeScope?: string;
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

// A lighter, secondary nav: muted by default so it never competes with the content; the active page
// reads in ink, and any link inks in on hover.
const navCls = (active: boolean) =>
  `bg-transparent border-0 p-0 cursor-pointer font-sans text-sm underline-offset-2 hover:underline ${
    active ? "text-ink underline" : "text-muted hover:text-ink"
  }`;

/** The slim persistent band: title, nav, and (multi-scope only) the compact scope switcher. The
 *  framing lives once on the landing, the corpus provenance in the "About this corpus" disclosure,
 *  and the discretion note is its own compact line, so this band stays short on every page. */
export function Header({ kiosk, view, onView, onAsk, scopes, activeScope, onSwitchScope }: Props) {
  return (
    <header className="mb-4">
      <div className="flex items-start justify-between gap-6">
        <h1 className="font-serif text-2xl leading-tight">
          <button type="button" className="linkish no-underline font-serif text-2xl" onClick={() => onView(null)}>
            Archive Argues With Itself
          </button>
        </h1>
        {kiosk && <KioskQr />}
      </div>
      <nav
        className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-rule pt-2"
        aria-label="Pages"
      >
        <button
          type="button"
          className={navCls(view === null)}
          aria-current={view === null ? "page" : undefined}
          onClick={onAsk ?? (() => onView(null))}
        >
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
