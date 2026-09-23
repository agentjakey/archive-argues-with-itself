# Archive Argues With Itself

A scaffold for the public writeup. The numbers below are the current audited values
from the repo. Author: Jacob Ortiz. [Jacob: finish the prose in your own voice; the
draft sentences are a starting point, not final copy.]

Live: https://archive-argues-with-itself-production.up.railway.app
Repo: https://github.com/agentjakey/archive-argues-with-itself

## What it is

This is public AI over the Internet Archive's Democracy's Library. It works over the
Canadian government's own public-health record, as scanned and OCR'd by the Internet
Archive. It is an inspectable civic-memory tool, not a chatbot. The point is not fluent
answers. The point is that you can see the page behind every claim, see where the record
is thin, and see how the government's own wording changed from one decade to the next.

It serves two corpora, switchable in the app: the clean federal pilot (3,477 items,
745,893 passages; 1960-2009) and the national microlog microfiche corpus (13,539 items,
1,136,827 passages; 1963-2018, all provinces). The data is hosted on Cloudflare R2 and
cached to the deploy on boot, with the pilot also on a GitHub Release as a fallback.
[Jacob: the audit numbers below are the pilot's; the microlog audit is in reports/microlog/.]

## A worked example

Ask how Alberta health insurance coverage changed between the 1970s and the 1990s. The
tool retrieves the relevant pages, writes a short answer with a numbered citation on
each sentence, and lets you open the two scans side by side: a 1974 provincial
inventory describing universal coverage, and a 1998-99 statistical supplement counting
who was covered under the later plan. The same plan, described two ways, twenty-five
years apart. That comparison is the tool's center. [Jacob: add a sentence on why this
case matters to you.]

## The honesty layer

Every sentence the model writes is tied to a scanned page you can open. When the record
is too thin to answer, the tool abstains instead of guessing, and it names the terms no
retrieved page mentions. A coverage grid shows what the archive holds by decade and
jurisdiction, so a gap is visible rather than hidden. The compare view puts two pages
from different years next to each other, which is where the record argues with itself.

Harm-adjacent content in this record is handled with care rather than dropped: a
result that touches a sensitive historical topic carries a short contextual note and a
link to support, and the underlying scan is always shown.

## How it works

Retrieval is hybrid: a keyword (BM25) leg and a dense semantic leg over a multilingual
MiniLM index, fused by Reciprocal Rank Fusion, with a soft down-weight for poor OCR and
a demotion for front and back matter. Generation is deterministic, run at temperature 0
with the configured model (claude-haiku-4-5-20251001). Before any model call, a
term-coverage rule decides whether the evidence is thin: if a salient term in the
question appears in no retrieved page, the tool abstains. After the model writes, each
citation is checked by three structural tests: the cited passage exists, it was in the
evidence retrieved for that question, and it resolves to a recorded page. Text overlap
is never reported as correctness. A sentence that fails is dropped.

Measured on an audit run of all 50 evaluation questions with the shipped configuration,
labels and judgments by the author:

- Strict citation support, meaning every claim in the sentence appears in the cited
  page: 93.3% (166 of 178 kept sentences on the 35 answerable questions).
- Lenient support, supported or partly supported: 99.4% (177 of 178).
- Cited passages that resolve to a recorded page: 119 of 119.
- Abstention on questions the archive cannot answer: 10 of 15 in-sample, 9 of 10
  held out.
- False abstention on answerable questions: 0 of 35 in-sample, 1 of 5 held out.
- Retrieval recall@10 on the fully judged gold, before and after the retrieval changes:
  0.3470 to 0.4581.

## Coverage and limits

The pilot's record stops around 2009; scanned government publications with usable OCR
effectively end in the 2000s (the national microlog scope reaches 2018), and the tool
never claims to reach the present. Almost
half of the passages carry no date: 338,338 of 745,893, or 45.4%, and no date is ever
guessed. OCR quality is uneven: of 745,893 passages, 6,186 are in the low-quality
bucket and 191,881 in the medium bucket, and the trail shows the raw excerpt so you can
see what the model saw.

The abstention rule is lexical, so it is sensitive to phrasing. It covers a question
term only when a retrieved page contains that word. One held-out question about a 1976
federal program was refused because no retrieved passage used the word "federal," even
though the pages describing the program were present. This wording-sensitivity is a
known limitation. [Jacob: note the planned v2 stoplist work if you want to.]

## Where to see it

The live demo is at
https://archive-argues-with-itself-production.up.railway.app and the source is open at
https://github.com/agentjakey/archive-argues-with-itself. The evaluation gold, the
reports, and the scripts that recompute every number are in the repository.
