import { Page } from "./Page";

export function About() {
  return (
    <Page title="About">
      <p>
        The public record disagrees with itself across decades; this tool shows you the pages. It was built
        by Jacob Ortiz during the AI Builders Fellowship of the BC + AI Ecosystem, with the Internet Archive,
        whose collections, OCR and page images make it possible. The pilot corpus is 3,477 Canadian government
        public-health publications held by the Internet Archive, roughly 1960 to 2009.
      </p>
      <h3>Where the pages come from</h3>
      <p>
        Every page image you see is served by archive.org from the Internet Archive's own copies; this tool
        redistributes none of them. Each evidence card and citation links to the page on archive.org. The
        text the tool searches is the Internet Archive's existing OCR of those scans.
      </p>
      <h3>The publications</h3>
      <p>
        The documents are Canadian federal, Ontario and Alberta government publications and remain under their
        own terms. The tool adds no claims of ownership; it indexes, retrieves and cites.
      </p>
      <h3>Source</h3>
      <p>
        The code, the evaluation questions, the human labels and the reports are open source under the MIT
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
