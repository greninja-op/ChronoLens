"""LEARN — remember past incidents and adjust future behavior.

A closed loop shouldn't fight the same fire twice the same way. ChronoLens
reads its own incident ledger and, for a service that has breached before,
pre-provisions a higher baseline *before* any breach starts and acts earlier —
so a recurring incident stops happening at all.
"""
from __future__ import annotations

from dataclasses import dataclass

from .record import Ledger


@dataclass
class Memory:
    service: str
    incident_count: int          # past incidents seen for this service
    recurrence: int              # how many were the same "breach avoided"/escalated pattern
    recommended_floor: float     # extra baseline capacity units to pre-provision
    lead_window_s: float         # how far ahead to act (grows with recurrence)
    note: str

    @property
    def is_repeat_offender(self) -> bool:
        return self.incident_count >= 1  # acted before -> we've "learned" it


def recall(service: str, ledger: Ledger | None = None,
           *, base_lead_s: float = 120.0) -> Memory:
    """Build a memory profile for a service from the incident ledger."""
    ledger = ledger or Ledger()
    rows = [c for c in ledger.list() if c.get("service") == service]
    n = len(rows)
    # Each past incident makes us act a bit earlier and hold a bit more floor.
    floor = min(4.0, 2.0 * n)          # +2 capacity units per prior incident, capped
    lead = base_lead_s + 30.0 * min(n, 4)
    if n == 0:
        note = "No history — first encounter."
    else:
        note = (f"Seen {n} prior incident(s) on {service} — pre-provisioning "
                f"+{floor} capacity floor and acting {lead - base_lead_s:.0f}s earlier.")
    return Memory(service=service, incident_count=n, recurrence=n,
                  recommended_floor=floor, lead_window_s=lead, note=note)
