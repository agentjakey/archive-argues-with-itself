# Data flows

Every piece of data the site (archiveargues.org) and the engine (api.archiveargues.org) touch: where
it goes, who processes it, how long it is kept, and how that was checked. The public privacy page
(`web/src/components/pages/Privacy.tsx`) is built from this file; change both together.

Checked on 2026-10-31 against production release 2026-10-31.3 of the engine and the site release
deployed the same day. "Code" means the path was read and is covered by a test named here; "config"
means a committed configuration file; "live" means a request to production, made from a real
Chromium browser (Playwright) or with curl, as stated.

## The site in the browser

| What | Where it goes | Kept | How it was checked |
| --- | --- | --- | --- |
| Cookies | None set by archiveargues.org or api.archiveargues.org. | None | Live: Chromium visited every page, opened a story, an answer and the page drawer, and focused the question box; the browser context held no cookies afterwards and no response from either host carried `Set-Cookie`. |
| localStorage, sessionStorage, IndexedDB | Not used. | None | Code: no use in `web/src` (searched). Live: both storages empty after the visit above. |
| The page address | The question you ask is written into the address bar (`?q=`), so a link to the answer can be shared. It reaches Cloudflare only if the page is loaded with it (a reload, a shared link). | Cloudflare's own records only; this site keeps no request logs for the site (static assets, no Worker code runs) | Code: `web/src/lib/urlstate.ts`; config: `worker/site/wrangler.jsonc` (assets only, no `main`). |
| Third-party requests on load | `archive.org` and `*.us.archive.org` (scanned page images in the stories and answers). Nothing else. | Under the Internet Archive's policies | Live: every request host recorded in Chromium. |
| Third-party requests on use | `challenges.cloudflare.com` (Turnstile), only when you first click into the question box or ask. `archive.org` embed page (with its own scripts, analytics and a cookie), only after you press "Load the archive.org viewer here" in the page drawer. | Cloudflare: Turnstile Privacy Addendum. Internet Archive: its policies | Live, as above; before this change the embed loaded whenever the drawer opened, and it set `ia-csrf` and called archive.org analytics hosts. Code: `PageDrawer.test.tsx`. |
| Cloudflare Web Analytics | Off. Cloudflare still injects its beacon script into the HTML; the site's Content-Security-Policy does not allow its host, so the browser blocks it and no request is sent. | None | Live: Chromium reported the script blocked by CSP and no request to `cloudflareinsights.com` completed. Config: `site/static/_headers.template`; the release gate refuses a CSP that allows that host (`tests/test_release.py`). |
| Network error reports | Cloudflare's edge sends `NEL` and `Report-To` headers with `success_fraction 0`: a browser may report a failed request (the URL and error type) to `a.nel.cloudflare.com`. | Cloudflare | Live: response headers (curl). This is a Cloudflare zone default, not set by this repository. |

## A question

| Step | Data | Who processes it | Kept | How it was checked |
| --- | --- | --- | --- | --- |
| Turnstile | A challenge run by Cloudflare in the browser; the resulting single-use token is sent with the question in `x-turnstile-token`. The engine Worker sends the token, its secret and your IP address to Cloudflare's `siteverify`. | Cloudflare | Turnstile Privacy Addendum | Code: `worker/engine/src/guard.ts` `checkTurnstile`; tests in `worker/engine/test/worker.test.ts`. The IP is sent because siteverify uses it to tie the token to the visitor; it goes only to Cloudflare, which already receives it as the host. |
| Rate limit | A key made from your IP address and the release id (SHA-256, first 32 hex characters). Not secret: anyone with the release id could test a guessed address, so it is treated as personal data. | Cloudflare rate limiting binding (6 questions and 10 wakes per minute) | The binding's 60-second counter; never written to D1 or to any log | Code: `guard.ts` `clientKey`, `index.ts` (the only uses); config: `wrangler.jsonc` `ratelimits`. |
| Daily budget | One row per UTC day: the day and a count of model calls. No visitor identity. | Cloudflare D1 (`model_budget`) | Kept; holds no personal data | Code: `guard.ts` `takeModelBudget`; migration `0001_answer_cache.sql`. |
| Stored-answer lookup | The engine Worker computes the cache key from the question, the filters and the collection, and reads D1. | Cloudflare (Worker, D1) | Nothing written by a lookup | Code: `cache.ts` `servedHit`. |
| The engine | Method, URL and JSON body (question, filters, collection, the options the public may set). No IP address, user agent, referrer, cookie or Turnstile token. | Cloudflare Containers, in a location Cloudflare chooses | In memory while the container runs; the container's disk is reset when it sleeps | Code: `ask.ts` `bareRequest`/`engineRequest`; test "is ignored in production" asserts the forwarded headers are only `content-type`. |
| The model | The cleaned question and the text of the retrieved passages, with the fixed instructions. No identifiers or metadata. | Anthropic (Claude Haiku 4.5) | Anthropic deletes API inputs and outputs within 30 days, longer only to enforce its usage policy or by law, and does not train on them by default ([retention](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data), updated 2026-07-01; [training](https://privacy.claude.com/en/articles/7996868-is-my-data-used-for-model-training), updated 2026-08-18) | Code: `src/archive_debugger/generate/llm.py` `AnthropicLLM.draft` (model, max_tokens, system, one user message). |
| Coverage counts | `GET /coverage?q=...` carries the question in the URL to the engine Worker, which forwards a bare request while the engine is awake. | Cloudflare | The engine's in-memory coverage cache until it sleeps; never for a question with an email address or phone number | Code: `app.py` `coverage_view`; `tests/test_cache.py`. |

## Stored answers (D1 `answers_v2`)

A visitor's question produces at most one row. Columns: `key` (SHA-256 of the collection's
context, the normalized question and the filters; not salted, so someone holding the database and
guessing a question exactly could confirm it), `scope`, `curated` (0), `question` (NULL, always:
the Worker refuses a visitor row with question text), `response_json` (the answer's sentences, the
retrieved passages, the coverage block with the question's words removed and replaced by their
count and positions, care-topic flags, generation settings; the answer text can echo words of the
question), `extras_version`, `model`, `prompt_sha256`, `context`, `created_at`, `expires_at`.
No IP address, IP hash, user agent, token or session identifier is stored anywhere in D1.

| What | Kept | How it was checked |
| --- | --- | --- |
| A visitor row | 90 days from `created_at`; the engine sets it and the Worker caps it on write. A daily job at 04:00 UTC deletes expired rows. | Code: `cache.py` `RETENTION_DAYS`, `cache.ts` `cappedExpiry`, `purgeExpired`; tests `test_visitor_rows_expire_after_90_days` and "brings a later expiry forward". Migration `0002_visitor_retention_90.sql` brought earlier rows forward (production had none: 58 rows, all curated). |
| Deleted rows in D1's history | D1 Time Travel can restore the database to any point in the last 30 days (Workers Paid). It is always on. | [D1 Time Travel](https://developers.cloudflare.com/d1/reference/time-travel/). |
| A question with an email address or phone number | Answered; no row read or written, nothing in the coverage cache. | Code: `has_contact_details`; `test_a_question_with_contact_details_is_answered_but_never_cached`. |
| `nocache` from the public | Ignored in production: the stored answer is served and the engine never sees the flag. Staging honors it (`PUBLIC_NOCACHE`). | Code: `ask.ts`; tests "nocache from the public"; live: a production `POST /ask` with `nocache: true` for a curated question returned `x-answer-source: stored`. |
| Curated rows | The seed and story questions, with their text, kept with the exhibit. | `export_cache_sql.py` exports curated rows only. |

To delete a visitor's stored answer on request, `scripts/v2/delete_answer.py --question "..."`
prints the D1 command (it can match only the exact wording and filters).

## Logs

| Where | What | Kept | How it was checked |
| --- | --- | --- | --- |
| Workers Logs, engine Worker | Its own lines: route, collection, outcome, milliseconds; wake, sleep, snapshot and purge events with counts. Never a question, an address or a token. Invocation logs (which would record each request's URL, and so the question in `/coverage` and `GET /ask`) are off. | 7 days (Workers Paid) | Config: `wrangler.jsonc` `observability.logs.invocation_logs: false` (a test reads it). Code: every `log(...)` and `console.log` in `worker/engine/src`. Before this change invocation logs were on; any URL they recorded ages out within 7 days of 2026-10-31. |
| Workers Logs, container output | Startup and provisioning stages, timings (`[ask-timing]` with collection, milliseconds, outcome and passage count), cache read or write failures by error type. No access log, so no request line. | 7 days | Code: `docker/entrypoint.sh` (`--no-access-log`, tested), the `print` calls in `src/archive_debugger`. |
| Site Worker | No code runs; static asset requests produce no Workers Logs. | None | Config: `worker/site/wrangler.jsonc`. |
| Durable Object storage | Per engine: the last 50 wakes (release, timings, provisioning summary, exit), the last activity time, the snapshot id. No visitor data. | Until overwritten | Code: `container.ts`. |

## Robots, security contact and headers

`robots.txt` on the site allows crawling (except the hashed data shards) and names the sitemap; on
the engine it disallows everything. `/.well-known/security.txt` names security@archiveargues.org.
The Content-Security-Policy allows scripts only from the site and `challenges.cloudflare.com`,
frames only from Turnstile and archive.org, images from archive.org, and connections only to the
engine; the release gate refuses a policy that allows inline or eval scripts, a wildcard, or the
Web Analytics host.
