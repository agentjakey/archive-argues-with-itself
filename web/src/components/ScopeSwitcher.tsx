import { formatInt } from "../lib/format";
import type { ScopeInfo } from "../types";

interface Props {
  scopes: ScopeInfo[];
  active: string;                 // the active scope's name
  onSwitch: (name: string) => void;
}

/** The corpus switcher and the active corpus's identity. Hidden when only one corpus is
 *  served (the festival pilot), so a single-scope build is unchanged. Switching triggers a
 *  full reload into the chosen corpus, so no state from the other corpus can remain. */
export function ScopeSwitcher({ scopes, active, onSwitch }: Props) {
  if (scopes.length < 2) return null;
  const current = scopes.find((s) => s.name === active) ?? scopes[0];
  return (
    <div className="mt-4">
      <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Choose a corpus to explore">
        <span className="tag" aria-hidden="true">
          Corpus
        </span>
        {scopes.map((s) => {
          const on = s.name === current.name;
          return (
            <button
              key={s.name}
              type="button"
              className="chip"
              aria-pressed={on}
              onClick={() => {
                if (!on) onSwitch(s.name);
              }}
            >
              {s.label}
            </button>
          );
        })}
      </div>
      <p className="mt-2 text-sm text-muted" aria-live="polite">
        Exploring <span className="text-ink">{current.label}</span>
        {current.blurb ? ` (${current.blurb})` : ""}. Source:{" "}
        {current.collection && current.collection_url ? (
          <a className="linkish" href={current.collection_url} target="_blank" rel="noreferrer">
            {current.collection} on archive.org
          </a>
        ) : (
          "unknown"
        )}
        , {formatInt(current.item_count)} items.
      </p>
    </div>
  );
}
