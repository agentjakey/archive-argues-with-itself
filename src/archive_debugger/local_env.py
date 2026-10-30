"""The one rule for where configuration and secrets come from, for the server and the boot.

Precedence: a variable already set in the process environment always wins over the same name in
a local .env file. In production nothing is read from a file: Cloudflare passes the engine its
secrets (ANTHROPIC_API_KEY, CIVIC_CACHE_TOKEN, and the R2 key pair when it is used) as environment
variables from wrangler secrets, and the image holds no .env. On a development machine .env fills
in only what the shell has not set. So a stale key exported in a shell profile shadows the .env
key; the fix is to unset it in the shell (docs/v2/HOSTING.md, "Secrets").

Secret values are never printed. The startup log says, for each secret name, only whether it is
set and where it came from.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Optional

SECRET_NAMES = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CIVIC_CACHE_TOKEN",
                "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY")


def load_local_env(path: Optional[Path] = None, *, log: Optional[Callable[[str], None]] = print) -> dict:
    """Load .env without overriding the environment, then log where each secret came from.
    Returns {name: "environment" | ".env" | "unset"} for the secret names."""
    from dotenv import load_dotenv

    before = {name: bool(os.environ.get(name)) for name in SECRET_NAMES}
    load_dotenv(path, override=False)
    sources = {}
    for name in SECRET_NAMES:
        if before[name]:
            sources[name] = "environment"
        elif os.environ.get(name):
            sources[name] = ".env"
        else:
            sources[name] = "unset"
    if log is not None:
        listed = ", ".join(f"{name}={source}" for name, source in sources.items())
        log(f"[env] secrets present by source (values never logged): {listed}")
    return sources
