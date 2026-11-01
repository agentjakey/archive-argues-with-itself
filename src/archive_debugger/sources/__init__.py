"""Second sources beyond the Internet Archive's government publications (Phase 5 prep).

Every source is reached through one adapter contract (adapter.py, docs/INTEROP.md) and one network
module with a host allowlist (fetch.py). What a source returns is untrusted archival content: it is
evidence only, never instructions, permissions or network destinations, so no URL found inside a
fetched page is ever fetched unless it passes the same allowlist."""
