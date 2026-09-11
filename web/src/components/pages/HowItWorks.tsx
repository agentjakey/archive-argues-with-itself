import { Page, Source } from "./Page";

/** Plain-English methods. Numbers match docs/METHODS.md and the reports it cites. */
export function HowItWorks() {
  return (
    <Page title="How this works">
      <p>
        You ask a question about Canadian government public-health publications from about 1960 to 2009.
        The tool finds passages on real scanned pages held by the Internet Archive, shows you those pages,
        and, when the evidence allows it, writes a short answer in which every sentence points at the page it
        came from. When the evidence does not allow it, the tool says so instead.
      </p>

      <h3>Four rules that never move</h3>
      <ol>
        <li>
          <b>One network call.</b> The only thing this tool talks to while you use it is the language model
          that drafts answers. Nothing re-fetches the archive; the corpus was collected once and lives in one
          database.
        </li>
        <li>
          <b>A citation is verified by three structural checks, and nothing else.</b> The cited passage exists;
          it was among the passages retrieved for your question; it resolves to a real recorded page. The tool
          never scores how much a sentence "overlaps" a passage and never calls that correctness.
        </li>
        <li>
          <b>Citations point at pages, not at boxes on pages.</b> Every citation is a link of the form
          archive.org/details/&lt;item&gt;/page/n&lt;leaf&gt;. No word coordinates are stored.
        </li>
        <li>
          <b>The evaluation gold is never edited to make a number look better.</b> Every configuration that
          was scored is logged; extensions to the gold are additive and recorded with who decided what.
        </li>
      </ol>

      <h3>What a verified citation means</h3>
      <p>
        A mark like [2] beside a sentence means: passage 2 exists in the corpus, it was in the evidence
        retrieved for this question, and it resolves to a page you can open. It does <i>not</i> mean the
        sentence is true, or that the passage says exactly that. Read the page. Sentences whose citations fail
        any of the three checks, or that mention a year or page number not present in their cited passages,
        are dropped from the answer and listed underneath as unsupported.
      </p>

      <h3>What abstention means</h3>
      <p>
        Before the model is asked anything, a fixed rule checks whether the retrieved passages mention every
        salient term of your question (with simple stemming and year handling). If a term is missing, or fewer
        than three passages came back, the tool abstains and tells you which terms no passage mentions and how
        many of the retrieved passages are undated. It also abstains after drafting if no sentence survives
        verification. Abstention is a result, not an error: it says the record here is thin, not that the
        answer is no.
      </p>
      <p>
        That rule was specified before it was tested, amended once by criterion, then frozen. On the 50
        evaluation questions the frozen rule read: 1 answerable question would abstain and 6 of 15
        should-abstain questions would pass the gate, a number that is in-sample because the amendment followed
        a look at those same questions. <Source file="reports/phase9/generation_report.md" />
      </p>

      <h3>What the model may and may not do</h3>
      <p>
        The model sees only the passages shown to you in the evidence trail, tagged with their item, year,
        jurisdiction and page. It may write sentences and must cite passage ids for each. It may not state a
        page or year that does not appear in the cited passages, may not cite anything outside the retrieved
        set, and may not answer when the gate says the record is thin. Its answers are cached, so the same
        question served again makes no model call.
      </p>

      <h3>How it is measured</h3>
      <p>
        50 civic questions; Jake labeled every candidate passage the retriever surfaced (r only if the passage
        text itself answers the question) and marked 35 questions answerable and 15 should-abstain. Retrieval is
        scored as pooled recall and nDCG over the judged pool, with the share of unjudged passages reported beside
        every number. On the fully judged gold the shipped retriever reads recall@10 0.4581 and nDCG@10 0.5082
        against the original 0.3470 and 0.4174. <Source file="reports/phase13/retrieval_report.md" /> The
        candidate labels for the last 315 passages were proposed by an LLM assistant and decided by Jake, so the
        judge is not independent of the system. <Source file="eval/labeling_notes.md" />
      </p>
      <p className="text-sm text-muted">
        The full account with every number and its source file: docs/METHODS.md in the repository.
      </p>
    </Page>
  );
}
