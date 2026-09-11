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
        to 0.8061 on the original gold. The evidence cards show the class as a small tag so you can judge it.{" "}
        <Source file="reports/phase13/sections_report.md" /> <Source file="reports/phase13/retrieval_report.md" />
      </p>

      <h3>Metadata dates can disagree with the text</h3>
      <p>
        Evaluation question q018, rank 25: the item is dated 1984 in its metadata, but the passage is H1N1 and
        2009 pandemic content dated 2010-10-22. The label was left as decided. Since the retrieval update an evidence card
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

      <h3>Verification checks support, not relevance</h3>
      <p>
        In the audit run (every question once, real model, final configuration) the tool abstained on 10 of the
        15 questions that should be abstained and answered 5 (q015, q030, q036, q037, q049). Each of those five is
        an all-supported answer to a different question than the one asked, on the wrong period or the wrong
        object: every sentence cites a real page that says what the sentence says. The three checks guarantee
        that a kept sentence is supported by its page; nothing guarantees the page is about what was asked. Read
        the pages. False abstentions on the 35 answerable questions: 0. On 15 held-out questions written after
        everything was frozen and never used in any sweep, 9 of 10 probes abstained and 4 of 5 answerable
        questions were answered. <Source file="reports/phase16/audit_report.md" />{" "}
        <Source file="reports/phase16/holdout_run.md" />
      </p>

      <h3>Two held-out misses, rule unchanged</h3>
      <p>
        "What did reports say about injuries from electric scooters?" was answered. The gate covers a word if
        any retrieved page contains it, and "scooters" was covered by an undated child-safety pamphlet (tricycles,
        carts, wagons and scooters under a child's care) and a 1988 occupational-health report (scooter steering
        under equipment maintenance). A lexical gate cannot tell electric scooters from toy or workplace scooters;
        every sentence is supported by its page and none is about the question. Same class as the five above.
      </p>
      <p>
        "What did federal reports say about the mass influenza vaccination program announced in 1976?" was
        abstained at the gate: "federal" counts as a salient word under the frozen rule, no retrieved page
        contains it, and the pages that describe the program name the federal government in other ways. The
        stoplist's actor-noun criterion holds "government", "department", "ministry" and "agency" but not
        "federal". Both results were recorded after a single held-out run and no rule was changed; "federal" is
        the first candidate for a v2 stoplist if one is ever opened.{" "}
        <Source file="reports/phase16/holdout_run.md" /> <Source file="docs/GAP_REPORT.md" />
      </p>

      <h3>What the audit measured</h3>
      <p>
        Every question once, the configured model, the shipped configuration; every kept sentence judged by the
        author against the full text of the pages it cites. Strict support (every claim in the cited text):
        93.3%, 166 of 178 sentences on the 35 answerable questions. Lenient (supported or partly): 99.4%, 177 of
        178. The 12 sentences that fell short added a date or a period, moved an attribution from a quoted body
        to the report's author, or, once, inverted a relation. Retrieval recall@10 on the fully judged gold:
        0.3470 before the retrieval changes, 0.4581 after. Cited passages resolving to a recorded page: 119 of
        119. <Source file="reports/phase16/audit_report.md" />
      </p>

      <h3>British Columbia is not a second scope here</h3>
      <p>
        Applying the corpus-choice method to BC: texts whose publisher or creator names British Columbia give
        590 public-health items, 278 of them dated 1960 to 2009, against the 2,500-item floor. Only 1 of 30
        sampled BC health texts sits in the Canadian-government portal collection this tool uses; the rest live
        in medical-library and microfiche collections. <Source file="reports/bc_audit/bc_sizing.md" />
      </p>

      <h3>The judge is not independent</h3>
      <p>
        All labels and judgments were decided by the author. To speed adjudication, candidate labels for the
        Phase 13 extension and the Phase 16 support judgments were first proposed by an assistant model and each
        was reviewed and decided by the author; the same model family generates the tool's answers, so this
        judge is not independent of the system. <Source file="eval/labeling_notes.md" />
      </p>
      <p className="text-sm text-muted">The full gap report with sources: docs/GAP_REPORT.md in the repository.</p>
    </Page>
  );
}
