import { formatInt } from "../../lib/format";
import { GOVERNANCE_STATEMENT } from "../../lib/sensitivity";
import type { ScopeInfo } from "../../types";
import { Ext, HELLO, LastUpdated, Page, POLICY_DATE, REPO_URL } from "./Page";

const DOCS = `${REPO_URL}/blob/main/docs`;

/** What the tool is and is not, who built it, how answers are made and how well they hold up. */
export function About({ scope }: { scope?: ScopeInfo | null }) {
  const cw = scope?.coverage_window;
  const window = cw && cw.min_year != null && cw.max_year != null ? `${cw.min_year} to ${cw.max_year}` : null;
  return (
    <Page title="About">
      <LastUpdated date={POLICY_DATE} />

      <h3>What this is</h3>
      <p>
        A search tool for Canadian government publications scanned by Internet Archive Canada. You ask a
        question; it finds pages in the record, shows them to you, and, when the pages allow it, writes a short
        answer in which every sentence points at the page it came from. When the pages do not answer the
        question, it says so.
        {scope && (
          <>
            {" "}
            The collection you are in, <span className="text-ink">{scope.label}</span>, holds{" "}
            {formatInt(scope.item_count)} public-health publications{window ? ` from ${window}` : ""}.
          </>
        )}
      </p>
      <p>
        It is not a general chatbot, not a source of advice, and not the archive itself. It searches a part of
        the collection, not all of it, and a page it did not find may still be in the archive.
      </p>

      <h3>Who built it</h3>
      <p>
        Jacob Ortiz built it as an independent project during the 2026 AI Builders Fellowship with the{" "}
        <Ext href="https://bc-ai.ca">BC + AI Ecosystem</Ext> and{" "}
        <Ext href="https://internetarchivecanada.org">Internet Archive Canada</Ext>. Neither organization, nor
        the Government of Canada, endorses the answers.
      </p>

      <h3>How answers are made</h3>
      <p>
        The tool searches the scanned pages and picks the passages that best match your question. Claude, an AI
        model made by Anthropic, then writes an answer from those passages only, and must cite a passage for
        every sentence. Deterministic checks run on every answer: a citation must point at a passage that was
        actually retrieved for your question and at a real recorded page; anything that fails is dropped or
        marked. The answers to the curated questions are also audited by hand. Even so, an answer can be wrong
        or can miss what matters, so open the page and check.
      </p>

      <h3>How well it holds up</h3>
      <p>
        In the hand audit of the federal pilot collection (50 questions), 93.3% of answer sentences were fully
        supported by the page they cite (166 of 178; 95% interval 88.6% to 96.1%), and the tool declined 10 of
        15 questions the record cannot answer (66.7%; 41.7% to 84.8%). In the national collection (47
        questions), 98.0% of sentences were fully supported (298 of 304; 95.8% to 99.1%), and it declined 5 of 7
        such questions (71.4%; 35.9% to 91.8%). One person, the author, did the judging. What was measured, how,
        and what the numbers do not say: <Ext href={`${DOCS}/ACCURACY.md`}>ACCURACY.md</Ext> and{" "}
        <Ext href={`${DOCS}/METHODS.md`}>METHODS.md</Ext>.
      </p>
      <p>
        A newer audit uses AI judges from two model families. The reference labels those judges are measured
        against come from AI adjudication: each item was read against its page and decided with a written reason.
        No human has checked those labels yet, and outside review is planned. Until it happens, treat the newer
        audit figures as AI measurements, not as human checks.
      </p>
      <p>
        Since 2 November 2026, new answers carry an evidence state (answered, partly answered, records disagree,
        not comparable, not enough evidence, restricted) and are written by GLM-5.3, an open-weight model, running
        on Cloudflare Workers AI, from pages found by keyword search. It replaced the earlier writer only after
        passing a test fixed in advance, on 839 questions it had never seen:{" "}
        <Ext href={`${DOCS}/ACCURACY.md#the-confirmatory-test-confirm-1-2026-11-02-promoted`}>the promotion test</Ext>,
        with what it does not show. Answers reviewed earlier keep the version they were reviewed under.
      </p>

      <h3>Where the pages come from</h3>
      <p>
        The pages and their text come from Internet Archive Canada's scans on archive.org. Page images are loaded
        from archive.org as you read; this site does not copy them. Every citation links to its page there.
      </p>

      <h3>Credit</h3>
      <p>
        The way this site is built and checked, compiled into static files with gates before each release,
        learns from <Ext href="https://github.com/AbstractsMachine/qipu-vancouver">Qipu</Ext>.
      </p>

      <h3>Care</h3>
      <p>
        Some of this material describes harm, including harm done to Indigenous communities through the health
        system. It stays searchable and cited, but it is kept out of the featured stories.
      </p>
      <p>{GOVERNANCE_STATEMENT}</p>

      <h3>Open source and contact</h3>
      <p>
        The code, the evaluation questions, the labels and the reports are open source under the MIT licence:{" "}
        <Ext href={REPO_URL}>github.com/agentjakey/archive-argues-with-itself</Ext>. Questions, corrections or
        anything else: <a className="linkish" href={`mailto:${HELLO}`}>{HELLO}</a>.
      </p>
    </Page>
  );
}
