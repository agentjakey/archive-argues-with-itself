# Privacy

The full privacy page is on the site: https://archiveargues.org/?view=privacy. Every piece of data
the site and the engine touch, with how each was checked, is in `docs/DATA_FLOWS.md`. In short
(last updated 2026-10-31):

- No accounts, no ads, no cookies and no tracking on the site, and nothing is sold.
- A visitor's question is not stored as text. Its answer is stored under a one-way key made from the
  question, with the question's words removed from the stored coverage block, and deleted after 90
  days (D1's history can restore deleted rows for up to 30 more days). A question that contains an
  email address or a phone number is answered but never stored. The answers to the published seed
  and story questions are kept with their questions, as part of the exhibit.
- The question and the retrieved page text are sent to Anthropic to write the answer. Anthropic
  deletes API inputs and outputs within 30 days unless it must keep them longer to enforce its
  usage policy or by law, and does not train on them by default.
- The engine receives the question only, without the visitor's address or browser details. Logs
  hold routes, outcomes and timings, never a question or an address, for 7 days.
- Rate limiting uses a hash of the visitor's address held by Cloudflare for one minute; it is never
  written to the database or to logs.
- This site uses Cloudflare Turnstile to tell people from bots. Its use is governed by the Turnstile
  Privacy Addendum (https://www.cloudflare.com/turnstile-privacy-policy/).
- Page images load from archive.org. The archive.org page viewer, which sets its own cookies, loads
  only when a visitor asks for it.
- Deletion requests: hello@archiveargues.org, with the question's text and roughly when it was
  asked. The question feature is for people 18 and over.

Changes are dated and logged in `CHANGELOG.md`.
