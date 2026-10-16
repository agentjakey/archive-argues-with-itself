import { ATTRIBUTION_NOTICE } from "../lib/sensitivity";

/** The tool's own attribution-incomplete acknowledgement (CARE-aligned, in the spirit of the Local
 *  Contexts Attribution Incomplete Notice), shown alongside the care note and the interstitial for
 *  records created about an Indigenous community by the state without that community's involvement.
 *  It is NOT an official Local Contexts Notice; it is the tool's own words, additive, and it never
 *  alters the record. A lighter rule than the surrounding note so it reads as a distinct, subordinate
 *  acknowledgement and does not crowd the crisis lines. Static, works offline. */
export function AttributionNotice() {
  return (
    <div className="mt-3 border-l border-rule pl-3" aria-label="A note on attribution">
      <p className="font-sans text-xs uppercase tracking-wide text-muted">{ATTRIBUTION_NOTICE.eyebrow}</p>
      <p className="mt-1 max-w-prose text-sm leading-relaxed">{ATTRIBUTION_NOTICE.body}</p>
    </div>
  );
}
