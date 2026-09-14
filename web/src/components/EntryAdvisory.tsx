import { ENTRY_ADVISORY } from "../lib/sensitivity";

/** Persistent, small historical-language and content advisory at app entry. Always present,
 *  quiet, non-blocking. Copy lives in lib/sensitivity. Static, works offline. */
export function EntryAdvisory() {
  return (
    <p className="rule-left my-3 max-w-prose text-sm text-muted" role="note" aria-label="Content advisory">
      {ENTRY_ADVISORY}
    </p>
  );
}
