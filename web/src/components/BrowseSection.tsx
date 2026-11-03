import { formatInt } from "../lib/format";
import type { View } from "../lib/urlstate";
import type { CatalogueSummary } from "../hooks/useCatalogueSummary";
import type { ScopeInfo } from "../types";

interface Props {
  scopes: ScopeInfo[] | null;
  catalogue: CatalogueSummary | null;
  onView: (view: View) => void;
}

/** Ways in without a question: through time, across the country, the collections searched here, and
 *  the whole catalogue. Every figure is read from the release's own data (the corpora's composition
 *  and the catalogue summary); a figure that has not loaded is left out rather than guessed. */
export function BrowseSection({ scopes, catalogue, onView }: Props) {
  const items = (scopes ?? []).reduce((n, s) => n + s.item_count, 0);
  const known = catalogue?.documents ?? null;
  const indexed = catalogue?.coverage?.indexed ?? null;
  return (
    <section className="browse" aria-labelledby="browse-heading">
      <h2 id="browse-heading" className="section-title">
        Explore without a question
      </h2>
      <ul className="browse-grid">
        <li>
          <BrowseCard
            title="Through time"
            body="See when a topic appears in the record, decade by decade, and set two decades side by side."
            onClick={() => onView("timeline")}
          />
        </li>
        <li>
          <BrowseCard
            title="Across Canada"
            body="A map of where the searchable documents come from, province by province, with the gaps shown."
            onClick={() => onView("map")}
          />
        </li>
        <li>
          <BrowseCard
            title="The collections"
            body={
              items > 0
                ? `The ${formatInt(items)} documents answers are drawn from: what they cover, how well they were scanned, and what is missing.`
                : "The documents answers are drawn from: what they cover, how well they were scanned, and what is missing."
            }
            onClick={() => onView("explore")}
          />
        </li>
        <li>
          <a className="browse-card" href="/catalogue/">
            <span className="browse-title">Every catalogue record</span>
            <span className="browse-body">
              {known != null
                ? `All ${formatInt(known)} publications in the catalogue, by decade, place and issuer` +
                  (indexed != null ? `; ${formatInt(indexed)} of them have searchable text so far.` : ".")
                : "Every publication in the catalogue, by decade, place and issuer, including those whose text is not searchable yet."}
            </span>
          </a>
        </li>
      </ul>
    </section>
  );
}

function BrowseCard({ title, body, onClick }: { title: string; body: string; onClick: () => void }) {
  return (
    <button type="button" className="browse-card" onClick={onClick}>
      <span className="browse-title">{title}</span>
      <span className="browse-body">{body}</span>
    </button>
  );
}
