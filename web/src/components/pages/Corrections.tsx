import { GOVERNANCE_STATEMENT } from "../../lib/sensitivity";
import { Ext, HELLO, LastUpdated, Page, POLICY_DATE, REPO_URL } from "./Page";

export function Corrections() {
  return (
    <Page title="Corrections and care">
      <LastUpdated date={POLICY_DATE} />

      <h3>Asking for a change</h3>
      <p>
        Email <a className="linkish" href={`mailto:${HELLO}`}>{HELLO}</a> to ask for any of these:
      </p>
      <ul>
        <li>a correction, when an answer, a caption or a page on this site gets something wrong;</li>
        <li>a content note, when material needs a warning or context before it is shown;</li>
        <li>a restriction, when material should not be featured or should be harder to reach;</li>
        <li>a removal, when material should not be shown here at all.</li>
      </ul>
      <p>
        Include the page link or the question, and what you would like done. I aim to reply within a week.
      </p>

      <h3>How decisions are recorded</h3>
      <p>
        Requests and decisions are logged publicly, without personal details, in the{" "}
        <Ext href={`${REPO_URL}/blob/main/CHANGELOG.md`}>CHANGELOG</Ext>. Answers written by the AI model are
        never edited after the fact. A correction to an answer is a dated note shown beside it, and the original
        stays visible.
      </p>

      <h3>What the care layer is today</h3>
      <p>
        Some records describe harm, including harm done to Indigenous communities. The tool watches for such
        material: it keeps it out of the featured stories, shows a note and, where it fits, support lines before
        the material, and never uses it as a hook or uses period terms that are now offensive as labels.
      </p>
      <p>
        It does not claim compliance with the CARE Principles or OCAP. No Local Contexts Labels have been
        assigned by me; Labels are made by communities, and none have been applied to these records here.
      </p>
      <p>{GOVERNANCE_STATEMENT}</p>
    </Page>
  );
}
