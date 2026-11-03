import { cardId } from "../lib/citations";
import { shortTitle, yearLabel } from "../lib/format";
import type { EvidenceRow } from "../types";
import { CopyButton } from "./ShareBar";

interface Props {
  numbered: Map<string, number>;
  byId: Map<string, EvidenceRow>;
}

/** The numbered sources as plain text, one per line, each with its page and its archive.org link,
 *  for pasting into notes or a bibliography. */
export function citationText(numbered: Map<string, number>, byId: Map<string, EvidenceRow>): string {
  return [...numbered.entries()]
    .map(([id, n]) => {
      const r = byId.get(id);
      if (!r) return `${n}. ${id}`;
      const page = r.printed_page ? `p. ${r.printed_page} (leaf ${r.leaf_index})` : `leaf ${r.leaf_index}`;
      return `${n}. ${r.title ?? "Untitled"} (${yearLabel(r.year)}), ${page}. ${r.deep_link}`;
    })
    .join(String.fromCharCode(10));
}

/** "1. Short title (1999), p. 12 (leaf 12), archive.org" with jump-to-card. */
export function Sources({ numbered, byId }: Props) {
  if (!numbered.size) return null;
  const jump = (id: string) =>
    document.getElementById(cardId(id))?.scrollIntoView({ behavior: "smooth", block: "center" });
  return (
    <section className="mt-5" aria-labelledby="sources-heading">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 id="sources-heading" className="font-serif text-lg">
          Sources
        </h3>
        <CopyButton text={() => citationText(numbered, byId)} label="Copy citations" done="Citations copied" />
      </div>
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
              <button type="button" className="linkish" onClick={() => jump(id)} title={r.title ?? "Jump to the evidence card"}>
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
