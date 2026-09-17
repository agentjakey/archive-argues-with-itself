import type { ScopeInfo } from "../types";

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
