import type { ScopeInfo } from "../types";

interface Props {
  scopes: ScopeInfo[];
  active: string;                 // the active scope's name
  onSwitch: (name: string) => void;
}

/** The compact corpus switcher: just the chips. Hidden when only one corpus is served (the festival
 *  pilot), so a single-scope build is unchanged. Switching triggers a full reload into the chosen
 *  corpus, so no state from the other corpus can remain. The corpus's identity and source (blurb,
 *  collection on archive.org, item count) live in the "About this corpus" disclosure, not repeated
 *  full-size under the header on every page. */
export function ScopeSwitcher({ scopes, active, onSwitch }: Props) {
  if (scopes.length < 2) return null;
  const current = scopes.find((s) => s.name === active) ?? scopes[0];
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2" role="group" aria-label="Choose a corpus to explore">
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
  );
}
