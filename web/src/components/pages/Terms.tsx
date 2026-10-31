import { Ext, HELLO, LastUpdated, Page, POLICY_DATE, REPO_URL } from "./Page";

export function Terms() {
  return (
    <Page title="Terms of use">
      <LastUpdated date={POLICY_DATE} />

      <h3>Free and as is</h3>
      <p>
        This site is free to use and provided as is, without warranty of any kind. It may change, slow down or
        stop without notice.
      </p>

      <h3>Answers can be wrong</h3>
      <p>
        Answers are written by an AI model from the pages the tool found. They can be wrong, incomplete or out of
        date, and they are not legal, medical or financial advice. Open the cited page and check it before you
        rely on anything here.
      </p>

      <h3>Acceptable use</h3>
      <ul>
        <li>No automated use of the question feature: no scripts, bots or bulk querying.</li>
        <li>No getting around the rate limits, the person check or any other security measure.</li>
        <li>No personal information about other people in questions.</li>
      </ul>
      <p>Abuse may be rate-limited or blocked.</p>

      <h3>Code and data</h3>
      <p>
        The project's code and its own data (the evaluation questions, labels and reports) are under the MIT
        licence, as stated in the <Ext href={REPO_URL}>repository</Ext>. That licence does not cover the
        documents.
      </p>

      <h3>The documents</h3>
      <p>
        The documents belong to their publishers, mostly Canadian federal and provincial governments under Crown
        copyright. This site shows short cited excerpts for research and education. The full scans are on the{" "}
        <Ext href="https://archive.org">Internet Archive</Ext>, under its terms.
      </p>

      <h3>Rights holders</h3>
      <p>
        If you hold rights in a document shown here and want an excerpt changed or removed, email{" "}
        <a className="linkish" href={`mailto:${HELLO}`}>{HELLO}</a> with the page link and what you would like
        done. Requests are logged as described on the Corrections and care page.
      </p>
    </Page>
  );
}
