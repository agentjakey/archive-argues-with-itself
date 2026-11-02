"""The spend ledger (docs/formats/audit.md) and the hard cap.

Every paid call is checked before it is made: the worst case (the estimated input and the full
max_tokens of output, at list price) must fit under both the run's cap and the phase cap, counting
what has been spent and what is reserved for batches still in flight. A call that could cross
either cap is not made. After a call, its actual cost from the provider's token counts is recorded.
A batch reserves its worst case when it is submitted; the reservation is replaced by the actual
cost when its results are read, so a crash leaves the ledger erring high, never low."""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from archive_debugger.audit import prices
from archive_debugger.audit.records import append_jsonl, iter_jsonl

PHASE_CAP_USD = 25.00          # used only when config/audit.toml names no cap for the current phase
LEGACY_PHASE = "phase2"        # ledger entries written before entries carried a phase
AUDIT_CONFIG = Path(__file__).resolve().parents[3] / "config" / "audit.toml"


def phase_settings(path: Path = AUDIT_CONFIG) -> tuple:
    """(current phase, its cap in US dollars) from [budget] in config/audit.toml."""
    import tomllib
    try:
        with Path(path).open("rb") as fh:
            raw = tomllib.load(fh).get("budget") or {}
    except FileNotFoundError:
        raw = {}
    phase = raw.get("phase") or LEGACY_PHASE
    cap = float((raw.get("caps") or {}).get(phase, PHASE_CAP_USD))
    return phase, cap


class BudgetExceeded(Exception):
    pass


@dataclass
class Totals:
    spent: float
    reserved: float
    by_provider: dict

    @property
    def committed(self) -> float:
        return self.spent + self.reserved


class Ledger:
    def __init__(self, path: Path, *, phase: Optional[str] = None, phase_cap: Optional[float] = None, clock=time.time):
        configured_phase, configured_cap = phase_settings()
        self.path = Path(path)
        self.phase = phase or configured_phase
        self.phase_cap = configured_cap if phase_cap is None else phase_cap
        self.clock = clock
        # A check and the reservation it allows are one step, and no entry is read while another
        # thread is writing one.
        self._lock = threading.RLock()
        # The ledger only grows (appends from this and other processes), so entries already read are
        # kept and only the complete lines after them are read on the next check. A file that got
        # shorter is read again from the start.
        self._read: list = []
        self._offset = 0

    def _entries(self) -> list:
        with self._lock:
            try:
                size = self.path.stat().st_size
            except FileNotFoundError:
                self._read, self._offset = [], 0
                return []
            if size < self._offset:
                self._read, self._offset = [], 0
            if size > self._offset:
                with self.path.open("rb") as fh:
                    fh.seek(self._offset)
                    data = fh.read(size - self._offset)
                end = data.rfind(b"\n") + 1          # complete lines only; a line being written waits
                for line_no, raw in enumerate(data[:end].split(b"\n"), 1):
                    line = raw.strip()
                    if not line:
                        continue
                    try:
                        self._read.append(json.loads(line.decode("utf-8")))
                    except json.JSONDecodeError as exc:
                        raise ValueError(f"{self.path}: byte {self._offset}: not a JSON line ({exc.msg})") from exc
                self._offset += end
            return list(self._read)

    def totals(self, run_id: Optional[str] = None, *, phase: Optional[str] = None) -> Totals:
        """Spend and open reservations for one run, or for the whole of this ledger's phase (or the
        phase named)."""
        spent = 0.0
        reserved: dict = {}
        by_provider: dict = {}
        wanted_phase = phase or self.phase
        for e in self._entries():
            if run_id is not None and e["run_id"] != run_id:
                continue
            if run_id is None and (e.get("phase") or LEGACY_PHASE) != wanted_phase:
                continue
            if e["kind"] == "spend":
                spent += e["usd"]
                by_provider[e["provider"]] = by_provider.get(e["provider"], 0.0) + e["usd"]
            elif e["kind"] == "reserve":
                reserved[e["reservation"]] = e["usd"]
            elif e["kind"] == "release":
                reserved.pop(e["reservation"], None)
        return Totals(spent=spent, reserved=sum(reserved.values()), by_provider=by_provider)

    def check(self, run_id: str, run_cap: float, worst_usd: float) -> None:
        """Raise BudgetExceeded when a call costing up to worst_usd could cross the run's cap or the
        phase cap."""
        phase = self.totals()
        run = self.totals(run_id)
        if phase.committed + worst_usd > self.phase_cap:
            raise BudgetExceeded(f"phase cap ${self.phase_cap:.2f}: committed ${phase.committed:.4f} + up to "
                                 f"${worst_usd:.4f} would cross it")
        if run.committed + worst_usd > run_cap:
            raise BudgetExceeded(f"run cap ${run_cap:.2f}: committed ${run.committed:.4f} + up to "
                                 f"${worst_usd:.4f} would cross it")

    def _write(self, entry: dict) -> None:
        entry.setdefault("at", round(self.clock(), 3))
        entry.setdefault("price_version", prices.PRICE_VERSION)
        entry.setdefault("phase", self.phase)
        with self._lock:
            append_jsonl(self.path, entry)

    def spend(self, run_id: str, provider: str, model: str, input_tokens: int, output_tokens: int, *,
              batch: bool = False, what: str = "") -> float:
        usd = prices.cost(model, input_tokens, output_tokens, batch=batch)
        self._write({"kind": "spend", "run_id": run_id, "provider": provider, "model": model, "batch": batch,
                     "input_tokens": input_tokens, "output_tokens": output_tokens, "usd": round(usd, 6), "what": what})
        return usd

    def reserve(self, run_id: str, run_cap: float, provider: str, model: str, reservation: str, worst_usd: float) -> None:
        with self._lock:
            self.check(run_id, run_cap, worst_usd)
            self._write({"kind": "reserve", "run_id": run_id, "provider": provider, "model": model,
                         "reservation": reservation, "usd": round(worst_usd, 6)})

    def release(self, run_id: str, reservation: str) -> None:
        self._write({"kind": "release", "run_id": run_id, "reservation": reservation, "usd": 0.0})

    def open_reservations(self, run_id: Optional[str] = None) -> list:
        open_: dict = {}
        for e in self._entries():
            if run_id is not None and e["run_id"] != run_id:
                continue
            if e["kind"] == "reserve":
                open_[e["reservation"]] = e
            elif e["kind"] == "release":
                open_.pop(e["reservation"], None)
        return list(open_.values())


def worst_case(model: str, prompt_chars: int, max_tokens: int, *, batch: bool = False) -> float:
    return prices.cost(model, prices.estimate_input_tokens("x" * prompt_chars), max_tokens, batch=batch)
