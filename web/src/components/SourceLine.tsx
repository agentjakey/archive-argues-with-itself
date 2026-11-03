import { listWords, partLabel } from "../lib/parts";
import type { RouterReport, ScopeInfo } from "../types";

/** Deliverable 2: a plain line, above each result, naming the active corpus and its source
 *  collection the cited passages are drawn from. Links out to the collection on archive.org. */
export function SourceLine({ scope }: { scope: ScopeInfo }) {
  return (
    <p className="text-sm text-muted" aria-label="Where this comes from">
      This answer draws only from <span className="text-ink">{scope.label}</span>
      {scope.collection && scope.collection_url ? (
        <>
          , the{" "}
          <a className="linkish" href={scope.collection_url} target="_blank" rel="noopener noreferrer">
            {scope.collection}
          </a>{" "}
          collection on archive.org.
        </>
      ) : (
        "."
      )}
    </p>
  );
}

/** Above a whole-collection answer: the parts the router searched, and any it left out with why. */
export function CollectionLine({ router, scopes }: { router: RouterReport; scopes: ScopeInfo[] | null }) {
  const searched = router.searched.map((p) => partLabel(p.shard, scopes));
  return (
    <div className="text-sm text-muted" aria-label="Where this comes from" data-testid="collection-line">
      <p>
        Searched across the whole collection. This answer draws on{" "}
        <span className="text-ink">{searched.length ? listWords(searched) : "no part"}</span>
        {searched.length === 1 ? ", the part that holds the question's words most often." : ", the parts that hold the question's words most often."}
      </p>
      {router.left_out.length > 0 && (
        <details className="mt-1">
          <summary className="cursor-pointer">Parts not searched for this question ({router.left_out.length})</summary>
          <ul className="mt-1">
            {router.left_out.map((p) => (
              <li key={p.shard}>
                {partLabel(p.shard, scopes)}: {p.reason ?? "not chosen"}
              </li>
            ))}
          </ul>
          {router.note && <p className="mt-1">{router.note}</p>}
        </details>
      )}
    </div>
  );
}
