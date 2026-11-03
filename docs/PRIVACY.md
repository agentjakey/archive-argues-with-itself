# Privacy

The full privacy page is on the site: https://archiveargues.org/?view=privacy. Every piece of data
the site and the engine touch, with how each was checked, is in `docs/DATA_FLOWS.md`. In short
(last updated 2026-11-03):

- No accounts, no ads, no cookies and no tracking on the site, and nothing is sold.
- A visitor's question is not stored as text. Its answer is stored under a one-way key made from the
  question, with the question's words removed from the stored coverage block, and deleted after 90
  days (D1's history can restore deleted rows for up to 30 more days). A question that contains an
  email address or a phone number is answered but never stored. The answers to the published seed
  and story questions are kept with their questions, as part of the exhibit.
- Since 2026-11-02 the question and the retrieved page text go to GLM-5.3, an open-weight model on
  Cloudflare Workers AI, to write the answer. Cloudflare says it does not keep Workers AI inputs or
  outputs after the request is processed and does not train on them
  (https://developers.cloudflare.com/workers-ai/platform/privacy/, updated 2026-10-16). The recorded
  answers to the published example and story questions were written earlier by Anthropic's Claude
  Haiku 4.5.
- A visitor who picks a light or dark theme that differs from their device setting has that one
  choice kept in their own browser's local storage (key "theme"). It is never sent to the site. Kiosk
  pages never store it.
- The engine receives the question only, without the visitor's address or browser details. Logs
  hold routes, outcomes and timings, never a question or an address, for 7 days.
- Rate limiting uses a hash of the visitor's address held by Cloudflare for one minute; it is never
  written to the database or to logs.
- This site uses Cloudflare Turnstile to tell people from bots. To verify a check, the engine sends
  its one-time token and the visitor's IP address to Cloudflare, which already receives the address
  as the site's host. Its use is governed by the Turnstile Privacy Addendum
  (https://www.cloudflare.com/turnstile-privacy-policy/).
- Page images load from archive.org. The archive.org page viewer, which sets its own cookies, loads
  only when a visitor asks for it.
- Deletion requests: hello@archiveargues.org, with the question's text and roughly when it was
  asked. The question feature is for people 18 and over.

Changes are dated and logged in `CHANGELOG.md`.
