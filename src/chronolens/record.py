"""RECORD — write a case file for every prevented incident.

A prevented outage leaves nothing behind, so ChronoLens keeps the receipts:
what was coming, what it did, and the proof it worked. Stack them up and you
get a scoreboard of outages that were on their way and never arrived.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field


@dataclass
class CaseFile:
    id: str
    at: str
    service: str
    predicted_breach_in_s: float | None
    p99_at_prediction_ms: float
    slo_ms: float
    action: str
    rollback: str
    verified: bool
    final_p99_ms: float
    peak_p99_ms: float
    outcome: str  # "breach avoided" | "escalated" | "watch-only"
    evidence: dict = field(default_factory=dict)


class Ledger:
    """Append-only JSON ledger of prevented incidents."""

    def __init__(self, root: str | None = None):
        self.root = root or os.getenv(
            "CHRONOLENS_LEDGER_ROOT",
            os.path.join(os.path.dirname(__file__), "..", "..", "ledger"),
        )
        os.makedirs(self.root, exist_ok=True)
        self.path = os.path.join(self.root, "incidents.json")

    def _load_raw(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return []

    def record(self, case: CaseFile) -> CaseFile:
        data = self._load_raw()
        data.append(asdict(case))
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        return case

    def list(self) -> list[dict]:
        return self._load_raw()

    def prevented_count(self) -> int:
        return sum(1 for c in self._load_raw() if c.get("outcome") == "breach avoided")

    def total_count(self) -> int:
        return len(self._load_raw())


def new_case(**kwargs) -> CaseFile:
    return CaseFile(
        id=uuid.uuid4().hex[:12],
        at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **kwargs,
    )
