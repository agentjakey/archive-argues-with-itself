import { formatInt } from "../../lib/format";
import type { ScopeInfo } from "../../types";
import { Page } from "./Page";

/** The jurisdiction description of the active corpus's publications. Per scope, never a
 *  hardcoded single-scope claim: the pilot is federal/Ontario/Alberta; the microlog scope is
 *  national (federal, provincial, and municipal); with no active scope, a neutral phrasing. */
function jurisdictionPhrase(scope: ScopeInfo | null | undefined): string {
  if (scope?.name === "microlog") return "Canadian federal, provincial, and municipal";
  if (scope?.name === "pilot") return "Canadian federal, Ontario and Alberta";
  return "Canadian";
}

export function About({ scope }: { scope?: ScopeInfo | null }) {
  const cw = scope?.coverage_window;
  const window = cw && cw.min_year != null && cw.max_year != null ? `${cw.min_year} to ${cw.max_year}` : null;
  return (
    <Page title="About">
      <p>
        The public record disagrees with itself across decades; this tool shows you the pages. It was built
        by Jacob Ortiz during the AI Builders Fellowship of the BC + AI Ecosystem, with the Internet Archive,
        whose collections, OCR and page images make it possible.{" "}
        {scope ? (
          <>
            The corpus you are exploring, <span className="text-ink">{scope.label}</span>, is{" "}
            {formatInt(scope.item_count)} Canadian government public-health publications held by the Internet
            Archive{window ? `, ${window}` : ""}.
          </>
        ) : (
          <>It works over Canadian government public-health publications held by the Internet Archive.</>
        )}
      </p>
      <h3>Where the pages come from</h3>
      <p>
        Every page image you see is served by archive.org from the Internet Archive's own copies; this tool
        redistributes none of them. Each evidence card and citation links to the page on archive.org. The
        text the tool searches is the Internet Archive's existing OCR of those scans.
      </p>
      <h3>The publications</h3>
      <p>
        The documents are {jurisdictionPhrase(scope)} government publications and remain under their own terms.
        The tool adds no claims of ownership; it indexes, retrieves and cites.
      </p>
      <h3>Source and live site</h3>
      <p>
        The live demo is at{" "}
        <a className="linkish" href="https://archive-argues-with-itself-production.up.railway.app" target="_blank" rel="noopener noreferrer">
          archive-argues-with-itself-production.up.railway.app
        </a>
        . The code, the evaluation questions, the human labels, and the reports are open source under the MIT
        licence at{" "}
        <a className="linkish" href="https://github.com/agentjakey/archive-argues-with-itself" target="_blank" rel="noopener noreferrer">
          github.com/agentjakey/archive-argues-with-itself
        </a>
        . The answers are drafted by a configured language model and cached; the model is the only network
        call the tool makes while you use it.
      </p>
    </Page>
  );
}
