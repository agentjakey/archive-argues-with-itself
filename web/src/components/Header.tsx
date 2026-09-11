import type { View } from "../lib/urlstate";
import type { CorpusFacts } from "../types";
import { CorpusStrip } from "./CorpusStrip";
import { KioskQr } from "./KioskQr";

interface Props {
  corpus: CorpusFacts | null;
  kiosk: boolean;
  view: View | null;
  onView: (view: View | null) => void;
}

const LINKS: { view: View; label: string }[] = [
  { view: "how", label: "How this works" },
  { view: "gaps", label: "Gaps" },
  { view: "about", label: "About" },
];

export function Header({ corpus, kiosk, view, onView }: Props) {
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
            publications, 1960 to 2009. Not a chatbot.
          </p>
        </div>
        {kiosk && <KioskQr />}
      </div>
      <nav className="mt-3 flex flex-wrap gap-x-5 text-sm" aria-label="Pages">
        <button type="button" className="linkish" aria-current={view === null ? "page" : undefined} onClick={() => onView(null)}>
          Ask
        </button>
        {LINKS.map((l) => (
          <button
            key={l.view}
            type="button"
            className="linkish"
            aria-current={view === l.view ? "page" : undefined}
            onClick={() => onView(l.view)}
          >
            {l.label}
          </button>
        ))}
      </nav>
      {view === null && <CorpusStrip corpus={corpus} />}
    </header>
  );
}
