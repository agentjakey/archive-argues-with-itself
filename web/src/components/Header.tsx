import { useEffect, useId, useRef, useState } from "react";
import type { View } from "../lib/urlstate";
import { KioskQr } from "./KioskQr";
import { ThemeToggle } from "./ThemeToggle";

interface Props {
  kiosk: boolean;
  view: View | null;
  onView: (view: View | null) => void;
  onAsk?: () => void;               // "Ask": return to the search AND focus the question box
}

type Section = "ask" | "explore" | "how";

// Which top-level section a page belongs to, so the current place stays obvious on every page.
const SECTION_OF: Record<View, Section | null> = {
  explore: "explore",
  timeline: "explore",
  map: "explore",
  sources: "explore",
  how: "how",
  gaps: "how",
  about: "how",
  privacy: null,
  terms: null,
  accessibility: null,
  corrections: null,
};

export function sectionOf(view: View | null): Section | null {
  return view === null ? "ask" : SECTION_OF[view];
}

/** The site header: the name, four destinations (Ask, Explore, Exhibit, How it works) and the theme
 *  switch. On a narrow screen the destinations fold into a Menu button. The exhibit is a separate
 *  page, so its entry is a plain link. */
export function Header({ kiosk, view, onView, onAsk }: Props) {
  const [open, setOpen] = useState(false);
  const menuId = useId();
  const menuButton = useRef<HTMLButtonElement>(null);
  const section = sectionOf(view);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        menuButton.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const go = (next: View | null) => {
    setOpen(false);
    if (next === null && onAsk) onAsk();
    else onView(next);
  };

  const links = (
    <>
      <NavItem label="Ask" current={section === "ask"} onClick={() => go(null)} />
      <NavItem label="Explore" current={section === "explore"} onClick={() => go("explore")} />
      {!kiosk && (
        <li>
          <a className="nav-link" href="/exhibit/">
            Exhibit
          </a>
        </li>
      )}
      <NavItem label="How it works" current={section === "how"} onClick={() => go("how")} />
    </>
  );

  return (
    <header className="site-header">
      <div className="site-header-row">
        <a
          className="brand"
          href="/"
          onClick={(e) => {
            e.preventDefault();
            go(null);
          }}
        >
          Archive Argues <span className="brand-tail">With Itself</span>
        </a>
        <nav aria-label="Main" className="nav-wide">
          <ul className="nav-list">{links}</ul>
        </nav>
        <div className="header-tools">
          {!kiosk && <ThemeToggle />}
          <button
            ref={menuButton}
            type="button"
            className="icon-button menu-button"
            aria-expanded={open}
            aria-controls={menuId}
            onClick={() => setOpen((o) => !o)}
          >
            <MenuIcon open={open} />
            <span className="menu-label">Menu</span>
          </button>
        </div>
        {kiosk && <KioskQr />}
      </div>
      <nav aria-label="Main" id={menuId} className="nav-narrow" hidden={!open}>
        <ul className="nav-list-narrow">{links}</ul>
      </nav>
    </header>
  );
}

function NavItem({ label, current, onClick }: { label: string; current: boolean; onClick: () => void }) {
  return (
    <li>
      <button type="button" className="nav-link" aria-current={current ? "page" : undefined} onClick={onClick}>
        {label}
      </button>
    </li>
  );
}

function MenuIcon({ open }: { open: boolean }) {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      {open ? (
        <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      ) : (
        <path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      )}
    </svg>
  );
}
