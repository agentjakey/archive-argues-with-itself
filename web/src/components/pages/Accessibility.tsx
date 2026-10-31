import { Ext, HELLO, LastUpdated, Page, POLICY_DATE, REPO_URL } from "./Page";

/** What was tested, on what date, and what is known not to work. Update the date and the list
 *  together whenever the checks are run again (web/e2e/a11y.e2e.ts). */
export function Accessibility() {
  return (
    <Page title="Accessibility">
      <LastUpdated date={POLICY_DATE} />

      <h3>The target</h3>
      <p>The site aims to meet the Web Content Accessibility Guidelines (WCAG) 2.2 at level AA.</p>

      <h3>What was tested</h3>
      <p>On 2026-10-31, at phone and laptop widths in Chromium:</p>
      <ul>
        <li>
          an automated check with axe-core (WCAG 2.0, 2.1 and 2.2 A and AA rules) on every page, on an answer
          with its evidence, and on the page drawer; issues it found were fixed, and it now reports none;
        </li>
        <li>
          a full keyboard pass: every page reached from the menu and the footer, a question asked and answered,
          a story opened, the page drawer opened and closed with focus kept inside it and returned afterwards,
          the filters, and the skip link.
        </li>
      </ul>
      <p>
        Automated checks find only some problems. The site has not been tested with screen-reader users or by an
        outside auditor. The checks are in the <Ext href={`${REPO_URL}/blob/main/web/e2e`}>repository</Ext>.
      </p>

      <h3>Known gaps</h3>
      <ul>
        <li>
          The scanned pages are images. Their text comes from optical character recognition, which is imperfect,
          especially on old typewritten or handwritten pages; the tool marks passages where the recognition looks
          poor. Tables and figures in scans are not described.
        </li>
        <li>The archive.org page viewer is archive.org's own page and is outside this site's control.</li>
        <li>
          The person check (Cloudflare Turnstile) is run by Cloudflare. Most people never see it; if it asks you to
          act and you cannot, email us.
        </li>
      </ul>

      <h3>Reporting a barrier</h3>
      <p>
        If something on this site does not work for you, email{" "}
        <a className="linkish" href={`mailto:${HELLO}`}>{HELLO}</a> with the page and what happened. I aim to reply
        within a week.
      </p>
    </Page>
  );
}
