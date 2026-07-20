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
    outcome: str  # "breach avoided" | "escalated" | "watch-only" | "suggested"
    # --- closed-loop fields ---
    load_onset_at: str = ""            # when the load/incident was first detected
    learning_applied: bool = False     # did LEARN pre-provision from past incidents?
    recommended_floor: float = 0.0     # extra baseline capacity pre-provisioned
    prior_incidents: int = 0           # how many times this service breached before
    scaled_down: bool = False          # did COOLDOWN give capacity back?
    capacity_before: float = 0.0
    capacity_after: float = 0.0
    cost_units_returned: float = 0.0   # capacity units released after the spike
    cooldown_note: str = ""
    # --- playbook / trust / cost / explanation ---
    signal: str = "load"               # dominant failure signal the playbook saw
    why: str = ""                       # why that action fits the signal
    confidence: float = 1.0            # forecast confidence (0..1)
    autonomy_mode: str = "auto"        # suggest | earn | auto
    proven_saves: int = 0              # verified saves on this service before now
    dollars_saved: float = 0.0         # $ value of capacity returned on cooldown
    seasonal_hour: int | None = None   # recurring hour-of-day, if any
    explanation: str = ""              # NL explanation (rule-based or LLM)
    explanation_source: str = ""       # "rule-based" | provider name
    notified: bool = False             # did we post to Slack/webhook?
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

    def total_cost_units_saved(self) -> float:
        """Sum of capacity units returned across all incidents (cost saved)."""
        return round(sum(float(c.get("cost_units_returned", 0) or 0) for c in self._load_raw()), 2)

    def total_dollars_saved(self) -> float:
        """Sum of the dollar value of capacity returned across all incidents."""
        return round(sum(float(c.get("dollars_saved", 0) or 0) for c in self._load_raw()), 2)

    def prior_incidents_for(self, service: str) -> int:
        return sum(1 for c in self._load_raw() if c.get("service") == service)

    def update_last(self, **fields) -> dict | None:
        """Patch the most recent case file (e.g. attach a later scale-down)."""
        data = self._load_raw()
        if not data:
            return None
        data[-1].update(fields)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        return data[-1]


def new_case(**kwargs) -> CaseFile:
    return CaseFile(
        id=uuid.uuid4().hex[:12],
        at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **kwargs,
    )
