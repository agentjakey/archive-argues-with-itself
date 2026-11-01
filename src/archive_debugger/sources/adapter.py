"""The adapter contract (docs/INTEROP.md): what any second source must hand the registry and the checks.

An adapter turns one source into SourceRecords. A record names the source and a stable identifier,
where it can be opened (a locator a reader can follow), its text, and its dates kept apart:
  publication  a date the document itself states, with the line it was read from and how;
  capture      when an archive captured it (web sources), from the archive's own record;
never one copied into the other. Its licence and rights are stated as the source gives them, or
unknown. The registry stores records as documents of their own archive ("wayback", ...) with
coverage "known" until they are indexed; nothing from a second source is ever presented as part
of the government publications collection."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Iterable, Optional, Protocol


@dataclass(frozen=True)
class DateEvidence:
    year: Optional[int]
    value: Optional[str]          # the date as found (ISO when it can be read that far)
    method: str                   # read_from_page_meta | read_from_page_text | archive_capture_timestamp | not_found
    evidence: Optional[str]       # the line or field it came from


@dataclass
class SourceRecord:
    archive: str                  # "wayback"
    identifier: str               # stable within the archive, for example "<timestamp>/<url>"
    locator: str                  # where a reader opens it (the archived capture)
    original_url: Optional[str]
    title: Optional[str]
    text: str
    publication: DateEvidence
    capture: DateEvidence
    licence: str = "unknown: the source states none"
    meta: dict = field(default_factory=dict)

    @property
    def text_sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    def problems(self) -> list:
        """What breaks the contract. A record with any problem is not stored."""
        out = []
        if not self.identifier or not self.locator:
            out.append("no identifier or locator")
        if self.publication.method == "archive_capture_timestamp":
            out.append("a capture date was given as the publication date")
        if self.capture.method not in ("archive_capture_timestamp", "not_found"):
            out.append("the capture date did not come from the archive's record")
        if self.publication.year is not None and self.publication.evidence is None:
            out.append("a publication year without the line it was read from")
        return out


class Adapter(Protocol):
    archive: str

    def records(self) -> Iterable[SourceRecord]: ...
