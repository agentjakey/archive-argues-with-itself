# Privacy

What the site and the engine keep about the questions people ask.

- **Questions from visitors are not stored as text.** When the engine answers a question that is
  not one of the seed or story questions, it stores the answer under a one-way hash of the
  question, with the answer, its evidence and its metadata. The words of the question are not
  stored: the answer's coverage block keeps only how many search terms the question had and which
  of them the record did not cover, and the words are put back from the question of whoever asks
  it again.
- **Stored answers to visitors' questions expire after 180 days.** A daily job deletes them. The
  answers to the published seed and story questions are kept, with their questions, because they
  are part of the exhibit.
- **Logs carry no questions and no addresses.** The engine Worker logs the route, the outcome and
  timings. Rate limiting uses a salted hash of the visitor's address, which is not stored.
- **The old hosting.** The answer cache from the Railway deployment held visitors' questions in
  the form the v1 engine used. Only the seed and story answers were moved; the old file is deleted
  with the Railway volume.
- **Cloudflare Turnstile** checks that a request comes from a browser before a question can wake
  the engine or reach the model. It runs invisibly and is subject to Cloudflare's Turnstile
  Privacy Addendum: https://www.cloudflare.com/turnstile-privacy-policy/
- **Anthropic** receives the question and the retrieved passages when a new answer is written,
  under Anthropic's commercial terms for the API.
- **No accounts, no cookies set by the site, no analytics.**
