import { Ext, HELLO, LastUpdated, Page, POLICY_DATE, REPO_URL } from "./Page";

interface Row {
  data: string;
  purpose: string;
  processor: string;
  location: string;
  retention: string;
}

// From docs/DATA_FLOWS.md, which says how each line was checked. Change both together.
const ROWS: Row[] = [
  {
    data: "Each request to archiveargues.org: your IP address, browser details and the page address (a question you asked can be part of that address)",
    purpose: "Deliver the pages, protect the site from attacks",
    processor: "Cloudflare",
    location: "Cloudflare's global network",
    retention: "Not logged by this site. Cloudflare keeps its own records under its privacy policy",
  },
  {
    data: "Scanned page images your browser loads from archive.org (your IP address and browser details, and that the request came from this site)",
    purpose: "Show the cited pages",
    processor: "Internet Archive",
    location: "United States",
    retention: "Under the Internet Archive's policies. The archive.org page viewer, which sets its own cookies, loads only if you ask for it",
  },
  {
    data: "Turnstile check, run when you first click into the question box or ask",
    purpose: "Tell people from bots before a question reaches the AI model",
    processor: "Cloudflare",
    location: "Cloudflare's global network",
    retention: "Under the Turnstile Privacy Addendum",
  },
  {
    data: "Your question and any filters, when you ask",
    purpose: "Find matching pages and write an answer",
    processor: "Cloudflare (the engine), Anthropic (the answer)",
    location: "United States and other countries",
    retention: "The question's text is not stored by this site; see the next rows",
  },
  {
    data: "The answer to your question, stored under a one-way code made from the question, without the question's text",
    purpose: "Answer the same question again without a new AI call",
    processor: "Cloudflare (D1 database)",
    location: "Western North America",
    retention: "Deleted after 90 days. Cloudflare's database history can restore deleted rows for up to 30 more days. Not stored at all if the question contains an email address or phone number",
  },
  {
    data: "Your question and the retrieved page text, sent to the AI model",
    purpose: "Write the answer",
    processor: "Anthropic",
    location: "United States and other countries",
    retention: "Deleted by Anthropic within 30 days, longer only if flagged under its usage policy; not used to train models",
  },
  {
    data: "A scrambled form of your IP address",
    purpose: "Limit how many questions one connection can ask per minute",
    processor: "Cloudflare (rate limiting)",
    location: "Cloudflare's global network",
    retention: "A counter that lasts one minute; never written to the database or logs",
  },
  {
    data: "A count of AI calls per day, with no visitor details",
    purpose: "Keep within a daily budget",
    processor: "Cloudflare (D1 database)",
    location: "Western North America",
    retention: "Kept; it holds no personal data",
  },
  {
    data: "Service logs: which route was used, the outcome, timings",
    purpose: "Keep the service running",
    processor: "Cloudflare (Workers Logs)",
    location: "Cloudflare's global network",
    retention: "7 days. They never contain your question or your IP address",
  },
];

export function Privacy() {
  return (
    <Page title="Privacy">
      <LastUpdated date={POLICY_DATE} />

      <h3>The short version</h3>
      <p>
        No accounts, no ads, no cookies and no tracking on this site, and nothing is sold. Questions are
        answered by an AI model at Anthropic, and a copy of each answer is kept for 90 days without the
        question's text. Please don't type personal information into questions.
      </p>

      <h3>What happens to your data</h3>
      <div className="table-frame" role="region" aria-label="What happens to your data" tabIndex={0}>
        <table className="stack-table" role="table">
          <thead>
            <tr role="row">
              <th scope="col" role="columnheader">Data</th>
              <th scope="col" role="columnheader">Why</th>
              <th scope="col" role="columnheader">Who processes it</th>
              <th scope="col" role="columnheader">Where</th>
              <th scope="col" role="columnheader">How long</th>
            </tr>
          </thead>
          <tbody>
            {ROWS.map((r) => (
              <tr key={r.data} role="row">
                <td role="cell" data-label="Data">{r.data}</td>
                <td role="cell" data-label="Why">{r.purpose}</td>
                <td role="cell" data-label="Who processes it">{r.processor}</td>
                <td role="cell" data-label="Where">{r.location}</td>
                <td role="cell" data-label="How long">{r.retention}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-sm text-muted">
        How each line was checked: <Ext href={`${REPO_URL}/blob/main/docs/DATA_FLOWS.md`}>DATA_FLOWS.md</Ext>.
      </p>

      <h3>Who processes it</h3>
      <p>
        Cloudflare hosts the site and the engine and provides the content network, security, Turnstile, the
        database (D1) and file storage (R2). Anthropic's model writes the answers. Anthropic says it deletes API
        inputs and outputs within 30 days unless it must keep them longer to enforce its usage policy or by law (
        <Ext href="https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data">
          Anthropic, data retention
        </Ext>
        ), and that it does not train models on inputs or outputs from its commercial products by default (
        <Ext href="https://privacy.claude.com/en/articles/7996868-is-my-data-used-for-model-training">
          Anthropic, model training
        </Ext>
        ). Your data may be processed in the United States and other countries.
      </p>
      <p>
        This site uses Cloudflare Turnstile to tell people from bots. Its use is governed by the Turnstile Privacy
        Addendum (
        <Ext href="https://www.cloudflare.com/turnstile-privacy-policy/">https://www.cloudflare.com/turnstile-privacy-policy/</Ext>
        ).
      </p>

      <h3>Please don't type personal information into questions</h3>
      <p>
        Questions are about public records. A question that contains an email address or a phone number is still
        answered, but its answer is never stored.
      </p>

      <h3>Deleting an answer</h3>
      <p>
        Email <a className="linkish" href={`mailto:${HELLO}`}>{HELLO}</a> with the question's text and roughly when
        you asked it, and the stored answer will be deleted.
      </p>

      <h3>Age</h3>
      <p>The question feature is for people 18 and over.</p>

      <h3>Changes</h3>
      <p>
        Changes to this page are dated here and logged in{" "}
        <Ext href={`${REPO_URL}/blob/main/CHANGELOG.md`}>CHANGELOG.md</Ext>.
      </p>
    </Page>
  );
}
