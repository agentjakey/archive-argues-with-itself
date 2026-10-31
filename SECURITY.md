# Security

## Reporting

If you find a security problem, please do not open a public issue. Email
security@archiveargues.org, or report it through a private security advisory on
the repository
(https://github.com/agentjakey/archive-argues-with-itself/security/advisories/new).
English or French is fine. I aim to reply within a week.

The same contact is published at https://archiveargues.org/.well-known/security.txt.

## What is in scope

The site at archiveargues.org is static files; the engine at api.archiveargues.org
is a Cloudflare Worker in front of a container that reads the corpus database and
vector index read-only. While answering, the only outside service the engine calls
is the configured language-model provider, and it never re-fetches the Internet
Archive at request time. The parts worth scrutiny are the engine Worker's guards
(Turnstile, rate limits, the daily model budget, which models and options the
public may use), the answer cache and what it stores, path handling on the
`/pages/` and static routes, and the checksum step that verifies data before
serving.

## Secrets

There are no secrets or keys in this repository. Keys are set as Wrangler secrets
or environment variables (see `.env.example` for local development); the real
`.env` is git-ignored and never committed. If you ever find a key in the tree or in
the history, report it as above and I will rotate it.
