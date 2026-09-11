# Security

## Reporting

If you find a security problem, please do not open a public issue. Report it
through a private security advisory on the repository
(https://github.com/agentjakey/archive-argues-with-itself/security/advisories/new),
or open a normal issue that says only "security" with no details and I will
follow up privately. I aim to reply within a week.

## What is in scope

This is a read-only tool over public documents. The realistic concerns are the
serve layer and the deploy path: the API reads the corpus database and vector
index read-only, the only outbound call it makes while serving is to the
configured language-model provider, and it never re-fetches the Internet
Archive at request time. Path handling on the `/pages/` and static routes, the
answer cache, and the download-on-boot checksum step are the parts worth
scrutiny.

## Secrets

There are no secrets or keys in this repository. The language-model API key is
read only from an environment variable (see `.env.example`); the real `.env` is
git-ignored and is never committed. If you ever find a key in the tree or in the
history, report it as above and I will rotate it.
