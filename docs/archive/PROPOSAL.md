# Proposal: The Archive Argues With Itself: A Civic Memory Debugger

> This is the original fellowship proposal, kept as written for provenance. Some
> specifics changed during the build: the pilot topic became public health rather
> than housing (housing did not clear the item floor in a clean government scope),
> the interface was built with Vite and React rather than Next.js, and the corpus
> reaches about 2009 rather than the present. See the README and docs/METHODS.md
> for what was actually built.

The Archive Argues With Itself: A Civic Memory Debugger

Project summary

I want to build an open-source interface for asking questions of Canada’s public record and seeing more than a synthesized answer. A query returns a time-ordered evidence trail: the relevant government pages, how official language changes, which jurisdictions are represented, and where the archive becomes sparse or uncertain.

The pilot will focus on one civic issue with enough material to support comparison, likely housing affordability. Someone could ask, “What did Canadian governments say was causing housing unaffordability in 1995, 2005, and 2025?” and inspect the actual pages behind each answer.

The core idea is to treat an archive as something that can have failure modes. Search should reveal both what the record says and what the record cannot safely support.

Public benefit

This would be useful to journalists, students, policy researchers, civic groups, and anyone trying to understand how government explanations change over time.

Most search interfaces reward finding an answer. This one would also make it easy to question the answer. Users could trace claims back to scanned pages, compare language across years, and see when a result is based on a dense record versus a thin or uneven one.

There is also a benefit to the archive itself. The same pipeline can surface recurring metadata gaps, OCR problems, missing dates, and jurisdictional blind spots. I would publish those findings alongside the tool so the project produces both a public interface and a concrete audit of the source material it depends on.

Proposed approach

I would start with a deliberately bounded pilot corpus rather than trying to index 48 TB. Using Internet Archive search and metadata APIs plus existing OCR derivatives, I would collect metadata and page-level text for a few thousand documents around one civic topic.

I would normalize dates, issuing bodies, and jurisdictions, then build hybrid retrieval over the page text. An LLM would synthesize only from retrieved passages. Every generated claim would carry a page-level source, and undated or weakly supported material would stay visibly uncertain.

The interface would have two linked views: an evidence timeline showing how language and claims change over time, and a coverage view showing where the archive is sparse by date, jurisdiction, or source.

I would evaluate retrieval and citation support on a hand-built set of civic questions before polishing the public demo. The likely stack is Python for ingestion and evaluation, a lightweight lexical/vector index, and a Next.js interface. The ingestion process would cache data and respect Internet Archive’s automated-access guidelines. Everything needed to rebuild the pilot would be open source.

Dataset interest

This idea depends on this collection because the interesting object is the public record itself: government publications produced across decades, institutions, and jurisdictions, with all of the inconsistencies that come with a real archive.

A normal web search collapses time and provenance. A general-purpose model can produce a fluent historical answer without showing whether the evidence is federal, provincial, recent, duplicated, undated, or simply absent. Here, those distinctions are the substance of the project.

The collection’s uneven coverage is especially valuable. Missing dates and geographic imbalance become visible signals rather than cleanup problems. The tool can ask: what can this archive support about a question, how has that support changed, and where should a user resist drawing a conclusion?

That makes the project specific to this archive. The goal is to expose the structure, evidence, and blind spots of Canadian public memory.

Work plan

Week 1: Audit the collection around 2–3 candidate civic topics, choose the one with the strongest longitudinal coverage, define the pilot corpus, and write a small evaluation set before building the interface.

Week 2: Build the reproducible ingestion pipeline using Internet Archive metadata and OCR. Normalize dates, jurisdiction, issuer, item IDs, and page references. Measure OCR and metadata failure modes as I go.

Week 3: Build retrieval and page-level citation. Test whether real questions return the right evidence before adding generation.

Week 4: Add temporal comparison and archive-coverage views. Make undated records, sparse periods, and jurisdictional imbalance explicit in the UI.

Week 5: Run a structured evaluation on retrieval quality, citation support, and failure cases. If the pilot corpus is too noisy or broad, narrow the topic or jurisdiction rather than filling gaps with model guesses.

Week 6: Polish the public demo, documentation, reproducible build scripts, and methods/results note. Release the repository and a short gap report describing what the build revealed about the collection.

Expected deliverable

A deployed open-source web application where a user can ask a question about the pilot civic topic and receive a source-grounded, time-aware view of the public record.

The application will provide a searchable evidence timeline with page-level links back to Internet Archive, a comparison view for seeing how official language changes over time, and a coverage view exposing undated or thin parts of the collection.

The release will also include the reproducible ingestion/indexing pipeline, a small evaluation suite for retrieval and citation support, and a public methods and gap report documenting what worked, what failed, and what the archive itself made difficult.

The code, processing steps, evaluation set, and documentation will remain publicly available so someone else can reproduce or extend the work.

Success metric

A public demo covering at least 2,500 archived items, evaluated on 50 prewritten civic questions, with every synthesized claim linked to a specific source page; at least 90% citation support on a manually audited sample; visible date and jurisdiction coverage indicators; and a reproducible open-source pipeline another builder can run or extend.

Relevant experience

I work across ML engineering, empirical AI research, and public-facing technical tools. A recurring theme in my work is making opaque systems inspectable: building evaluation interfaces, tracing evidence and failure modes, and turning messy data into something people can actually interrogate.

I co-authored a NeurIPS 2025 ML4PS workshop paper on transformer attention in high-energy physics, and I have since built independent projects around model behavior, interpretability, and evaluation. I also work in ML engineering on agent trust systems, where provenance, verification, and reliable behavior matter in production.

Outside research, I have shipped a production workflow platform for a real business and built public educational tooling around responsible AI. Those projects taught me to scope aggressively, test the hard technical assumption early, and ship interfaces that people other than the builder can actually use.

This fellowship sits directly at the intersection I care about: retrieval, evidence, evaluation, public-interest data, and an artifact that can be inspected rather than simply trusted. 
