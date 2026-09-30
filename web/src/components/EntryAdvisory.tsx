import { ENTRY_ADVISORY, ENTRY_ADVISORY_SHORT } from "../lib/sensitivity";

/** Persistent historical-language and content advisory at app entry. Always visible and reachable
 *  (an ethics requirement), but compact: one line, with the full advisory behind an expandable
 *  "why", so it is not a tall multi-line box repeated at full size on every page. Static, offline. */
export function EntryAdvisory() {
  return (
    <div className="rule-left my-3 max-w-prose text-sm text-muted" role="note" aria-label="Content advisory">
      <details className="advisory">
        <summary className="cursor-pointer">{ENTRY_ADVISORY_SHORT}</summary>
        <p className="mt-1">{ENTRY_ADVISORY}</p>
      </details>
    </div>
  );
}
