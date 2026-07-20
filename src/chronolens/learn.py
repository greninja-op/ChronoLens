"""LEARN — remember past incidents and adjust future behavior.

A closed loop shouldn't fight the same fire twice the same way. ChronoLens reads
its own incident ledger and, for a service that has breached before:

* pre-provisions a higher baseline *before* any breach starts, and
* acts earlier (a wider lead window), and
* detects **seasonality** — if a service tends to breach around the same hour of
  day, it flags that recurring window so a scheduler can pre-provision on time.

So a recurring incident stops happening at all.
"""
from __future__ import annotations

import time
from collections import Counter
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
    seasonal_hour: int | None = None   # recurring UTC hour-of-day it tends to breach
    seasonal_note: str = ""
    seasonal_due_now: bool = False     # are we inside/near that recurring window?

    @property
    def is_repeat_offender(self) -> bool:
        return self.incident_count >= 1  # acted before -> we've "learned" it


def _hour_of(row: dict) -> int | None:
    at = row.get("load_onset_at") or row.get("at") or ""
    # timestamps look like 2026-07-20T17:03:11Z
    try:
        return int(at[11:13])
    except (ValueError, IndexError):
        return None


def detect_seasonality(rows: list[dict], *, now_hour: int | None = None,
                       min_repeats: int = 2, window: int = 1) -> tuple[int | None, bool, str]:
    """Find a recurring hour-of-day and whether we're near it now.

    Returns ``(hour, due_now, note)``. A "season" is any UTC hour that shows up
    in at least ``min_repeats`` past incidents.
    """
    hours = Counter(h for h in (_hour_of(r) for r in rows) if h is not None)
    if not hours:
        return None, False, ""
    hour, count = hours.most_common(1)[0]
    if count < min_repeats:
        return None, False, ""
    now_hour = time.gmtime().tm_hour if now_hour is None else now_hour
    due = abs(now_hour - hour) <= window or abs(now_hour - hour) >= (24 - window)
    note = (f"Seasonal pattern: {count} past incidents cluster around "
            f"{hour:02d}:00 UTC" + (" — and that window is now." if due else "."))
    return hour, due, note


def recall(service: str, ledger: Ledger | None = None,
           *, base_lead_s: float = 120.0, now_hour: int | None = None) -> Memory:
    """Build a memory profile for a service from the incident ledger."""
    ledger = ledger or Ledger()
    rows = [c for c in ledger.list() if c.get("service") == service]
    n = len(rows)
    # Each past incident makes us act a bit earlier and hold a bit more floor.
    floor = min(4.0, 2.0 * n)          # +2 capacity units per prior incident, capped
    lead = base_lead_s + 30.0 * min(n, 4)

    season_hour, due_now, season_note = detect_seasonality(rows, now_hour=now_hour)
    # A due-now season justifies pre-provisioning even without a fresh trend.
    if due_now and floor < 2.0:
        floor = 2.0

    if n == 0:
        note = "No history — first encounter."
    else:
        note = (f"Seen {n} prior incident(s) on {service} — pre-provisioning "
                f"+{floor} capacity floor and acting {lead - base_lead_s:.0f}s earlier.")
        if season_note:
            note += " " + season_note
    return Memory(service=service, incident_count=n, recurrence=n,
                  recommended_floor=floor, lead_window_s=lead, note=note,
                  seasonal_hour=season_hour, seasonal_note=season_note,
                  seasonal_due_now=due_now)
