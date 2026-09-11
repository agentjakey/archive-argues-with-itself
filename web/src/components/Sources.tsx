import { cardId } from "../lib/citations";
import { shortTitle, yearLabel } from "../lib/format";
import type { EvidenceRow } from "../types";

interface Props {
  numbered: Map<string, number>;
  byId: Map<string, EvidenceRow>;
}

/** "1. Short title (1999), p. 12 (leaf 12), archive.org" with jump-to-card. */
export function Sources({ numbered, byId }: Props) {
  if (!numbered.size) return null;
  const jump = (id: string) =>
    document.getElementById(cardId(id))?.scrollIntoView({ behavior: "smooth", block: "center" });
  return (
    <section className="mt-5" aria-labelledby="sources-heading">
      <h3 id="sources-heading" className="font-serif text-lg">
        Sources
      </h3>
      <ol className="mt-2 text-sm space-y-1">
        {[...numbered.entries()].map(([id, n]) => {
          const r = byId.get(id);
          if (!r) {
            return (
              <li key={id} className="text-muted">
                {n}. <span className="font-mono">{id}</span>
              </li>
            );
          }
          const page = r.printed_page ? `p. ${r.printed_page} (leaf ${r.leaf_index})` : `leaf ${r.leaf_index}`;
          return (
            <li key={id}>
              {n}.{" "}
              <button type="button" className="linkish" onClick={() => jump(id)} title="Jump to the evidence card">
                {shortTitle(r.title, 60)} ({yearLabel(r.year)})
              </button>
              , {page},{" "}
              <a className="linkish" href={r.deep_link} target="_blank" rel="noopener noreferrer">
                archive.org
              </a>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
