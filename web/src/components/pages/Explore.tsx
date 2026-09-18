import { formatInt, shortTitle } from "../../lib/format";
import type { Example, Filters, ScopeInfo, YearWindow } from "../../types";
import { Page } from "./Page";

function pct(n: number, total: number): string {
  return total ? `${Math.round((n / total) * 100)}%` : "0%";
}

function spanLabel(w: YearWindow | undefined): string {
  if (!w || w.min_year == null || w.max_year == null) return "undated only";
  return `${w.min_year} to ${w.max_year}`;
}

interface Props {
  scopes: ScopeInfo[] | null;
  examplesByScope: Record<string, Example[]>;
  onExploreScope: (name: string) => void;
  onEnterQuestion: (name: string, text: string, filters: Filters) => void;
}

/** The topic and scope explorer: a whole-corpus roll-up over the corpora served right now, then a
 *  card per corpus with its live stats and a few seed questions. Every entry point (a corpus, or a
 *  seed question) selects that scope and lands on a cited answer plus the sources view. All figures
 *  are read from the live /scopes composition; nothing is hardcoded. */
export function ExplorePage({ scopes, examplesByScope, onExploreScope, onEnterQuestion }: Props) {
  return (
    <Page title="Explore the record">
      <p>
        Enter the record by corpus or by question. Pick a corpus to make it active and ask within it,
        or open a seed question to land straight on a cited answer. This is a way in, not a dashboard:
        every path below resolves to cited passages you can follow to the page on archive.org.
      </p>
      {!scopes || scopes.length === 0 ? (
        <p className="text-muted" aria-live="polite">
          Loading corpora.
        </p>
      ) : (
        <ExploreBody
          scopes={scopes}
          examplesByScope={examplesByScope}
          onExploreScope={onExploreScope}
          onEnterQuestion={onEnterQuestion}
        />
      )}
    </Page>
  );
}

function ExploreBody({ scopes, examplesByScope, onExploreScope, onEnterQuestion }: Props & { scopes: ScopeInfo[] }) {
  const totalItems = scopes.reduce((n, s) => n + s.item_count, 0);
  const totalPassages = scopes.reduce((n, s) => n + (s.composition?.passages ?? 0), 0);
  const mins = scopes.map((s) => s.composition?.dated_span.min_year).filter((x): x is number => x != null);
  const maxs = scopes.map((s) => s.composition?.dated_span.max_year).filter((x): x is number => x != null);
  const span = mins.length && maxs.length ? `${Math.min(...mins)} to ${Math.max(...maxs)}` : "undated only";
  const collections = Array.from(new Set(scopes.flatMap((s) => s.collections)));

  return (
    <>
      <section className="mt-4 border-t border-b border-rule py-3" aria-label="Whole-corpus roll-up">
        <h3 className="tag">Across {scopes.length === 1 ? "the corpus" : `all ${scopes.length} corpora`} served now</h3>
        <dl className="mt-2 flex flex-wrap gap-x-8 gap-y-2">
          <Figure value={formatInt(totalItems)} label="items" />
          <Figure value={formatInt(totalPassages)} label="passages" />
          <Figure value={span} label="dated span" />
          <Figure value={formatInt(collections.length)} label={collections.length === 1 ? "source collection" : "source collections"} />
        </dl>
        <p className="mt-2 text-sm text-muted">
          Items and passages are summed across the corpora served now; each corpus is a separate,
          non-overlapping Internet Archive collection, so the totals are the sums of the per-corpus
          figures below. With one corpus served this equals that corpus.
        </p>
      </section>

      {scopes.map((s) => (
        <ScopeCard
          key={s.name}
          scope={s}
          examples={examplesByScope[s.name] ?? []}
          onExplore={onExploreScope}
          onEnter={onEnterQuestion}
        />
      ))}
    </>
  );
}

function ScopeCard({
  scope,
  examples,
  onExplore,
  onEnter,
}: {
  scope: ScopeInfo;
  examples: Example[];
  onExplore: (name: string) => void;
  onEnter: (name: string, text: string, filters: Filters) => void;
}) {
  const c = scope.composition;
  const ocrTotal = c ? c.ocr.high + c.ocr.medium + c.ocr.low : 0;
  const topJur = c
    ? [...c.jurisdictions].filter((j) => j.name !== "unknown").sort((a, b) => b.items - a.items).slice(0, 4)
    : [];
  const seeds = examples.slice(0, 4);

  return (
    <section className="mt-8 border-t border-rule pt-5" aria-label={`${scope.label} corpus`}>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h3 className="font-serif text-xl">{scope.label}</h3>
        <button type="button" className="chip" onClick={() => onExplore(scope.name)}>
          Explore this corpus
        </button>
      </div>
      {scope.blurb && <p className="mt-1 text-sm text-muted">{scope.blurb}</p>}
      <p className="mt-2 text-sm">
        Source:{" "}
        {scope.collection && scope.collection_url ? (
          <a className="linkish" href={scope.collection_url} target="_blank" rel="noopener noreferrer">
            {scope.collection} on archive.org
          </a>
        ) : (
          "unknown"
        )}
        {scope.collections.length > 1 && (
          <span className="text-muted"> (plus {scope.collections.length - 1} sibling collections)</span>
        )}
      </p>

      {c && (
        <>
          <dl className="mt-3 flex flex-wrap gap-x-8 gap-y-2">
            <Figure value={formatInt(scope.item_count)} label="items" />
            <Figure value={formatInt(c.passages)} label="passages" />
            <Figure value={spanLabel(c.dated_span)} label="dated span" />
            <Figure value={pct(c.undated.passages, c.passages)} label="of passages undated" />
          </dl>
          <p className="mt-2 text-sm">
            <span className="tag">OCR</span> high {pct(c.ocr.high, ocrTotal)} &middot; medium{" "}
            {pct(c.ocr.medium, ocrTotal)} &middot; low {pct(c.ocr.low, ocrTotal)}
          </p>
          <p className="mt-1 text-sm">
            <span className="tag">Jurisdiction</span>{" "}
            {topJur.length
              ? topJur.map((j, i) => (
                  <span key={j.name}>
                    {i > 0 ? ", " : ""}
                    {j.name.replace(/_/g, " ")} {pct(j.items, scope.item_count)}
                  </span>
                ))
              : "none resolved"}
            {"; unknown "}
            {Math.round(c.jurisdiction_unknown_share * 100)}%
            {c.jurisdiction_is_floor ? " (proxy floor, not precise per-province coverage)" : ""}
          </p>
        </>
      )}

      <div className="mt-3">
        <span className="tag">Seed questions</span>
        {seeds.length ? (
          <div className="mt-2 flex flex-col gap-2">
            {seeds.map((e) => (
              <button
                key={e.qid}
                type="button"
                className="chip text-left"
                onClick={() => onEnter(scope.name, e.text, e.filters ?? {})}
                title="Open this question in this corpus"
              >
                {shortTitle(e.text, 80)}
              </button>
            ))}
          </div>
        ) : (
          <p className="mt-1 text-sm text-muted">No seed questions yet for this corpus; use Explore this corpus and ask your own.</p>
        )}
      </div>
    </section>
  );
}

function Figure({ value, label }: { value: string; label: string }) {
  return (
    <div className="flex flex-col">
      <dd className="font-serif text-xl m-0">{value}</dd>
      <dt className="text-sm text-muted">{label}</dt>
    </div>
  );
}
