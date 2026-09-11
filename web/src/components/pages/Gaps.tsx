import { Page, Source } from "./Page";

/** What the archive cannot tell you. Numbers match docs/GAP_REPORT.md and the reports it cites. */
export function Gaps() {
  return (
    <Page title="Gaps">
      <p>
        An archive argues with itself partly by what it leaves out. These are the gaps this tool knows about,
        with the numbers that measure them.
      </p>

      <h3>Almost half of the passages carry no date</h3>
      <p>
        338,338 of 745,893 passages (45.4%) belong to items with no usable date, after 36 items were dated from
        an explicit year in their titles. No date is ever guessed. Undated passages get their own lane on the
        timeline and their own row in the coverage grid.{" "}
        <Source file="reports/phase5/normalize_report.json" /> <Source file="reports/phase4/parse_report.md" />
      </p>

      <h3>The record stops around 2009</h3>
      <p>
        Among public-health items in the government-publications collection, 1,352 are dated 1990 to 2009, 44
        are dated 2010 or later, and 18 are dated 2015 or later. Scanned government publications with OCR
        effectively end in the 2000s, so the tool frames itself as 1960 to 2009 and never claims to reach the
        present. <Source file="reports/coverage_audit/finalist_sizing.md" />
      </p>

      <h3>Front and back matter, and what demotion did</h3>
      <p>
        Title pages, tables of contents, transmittal letters, indexes and reference lists match many queries
        while answering nothing. A deterministic classifier (leaf position plus text patterns, no labels, no
        model) marked 12,684 pages front matter and 3,823 back matter out of 448,496 pages with text. Its first
        version was about 60% precise on back matter because a citation pattern fired on years beside times and
        ratios in tables; the second version, needing a page range or an author entry with a nearby year, read 18
        of 20 on a fresh sample. Demoting those pages (score halved, never excluded) moved recall@20 from 0.6823
        to 0.8061 on the Phase 7 gold. The evidence cards show the class as a small tag so you can judge it.{" "}
        <Source file="reports/phase13/sections_report.md" /> <Source file="reports/phase13/retrieval_report.md" />
      </p>

      <h3>Metadata dates can disagree with the text</h3>
      <p>
        Evaluation question q018, rank 25: the item is dated 1984 in its metadata, but the passage is H1N1 and
        2009 pandemic content dated 2010-10-22. The label was left as decided. Since Phase 13 an evidence card
        says "mentions 2010 (item dated 1984)" whenever a passage's text names years well after its item's date;
        nothing is re-ranked and no side is taken. <Source file="eval/labeling_notes.md" />
      </p>

      <h3>Why public health, not housing</h3>
      <p>
        The proposal used housing as its example. Housing affordability yields 1,737 texts in the clean
        government scope (1,747 in the curated union), under the 2,500-item floor; only adding a microfiche-sourced
        collection (13,796) clears it, and that collection's OCR quality was never verified. Public health clears
        the floor cleanly with 3,477 items. <Source file="reports/coverage_audit/finalist_sizing.md" />
      </p>

      <h3>The abstention rule, tested twice</h3>
      <p>
        First sweep of the thinness rule on the 50 evaluation questions: 10 of 35 answerable questions would
        abstain and 4 of 15 should-abstain questions would answer. After one amendment by criterion, then
        frozen: 1 answerable would abstain (on the word "risks") and 6 of 15 should-abstain would answer. The
        amendment followed a look at the first sweep on these same questions, so the second number is in-sample
        and is not an estimate of how the rule behaves on questions it has not seen. On the final retriever the
        frozen rule reads 0 and 9; six probes still abstain on years or topics the archive does not hold.{" "}
        <Source file="reports/phase9/generation_report.md" /> <Source file="reports/phase13/retrieval_report.md" />
      </p>

      <h3>The judge is not independent</h3>
      <p>
        The last 315 gold labels were proposed by an LLM assistant from the worksheet excerpts and each was
        reviewed and decided by Jake. The same model family writes the answers.{" "}
        <Source file="eval/labeling_notes.md" />
      </p>
      <p className="text-sm text-muted">The full gap report with sources: docs/GAP_REPORT.md in the repository.</p>
    </Page>
  );
}
