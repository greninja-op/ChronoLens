"""Anti-flap guardrails — stop the loop fighting itself.

Autonomy without brakes oscillates: scale up, cool down, scale up again, forever.
These guardrails add three brakes, all persisted so they survive across CLI runs:

    dwell      don't act on the same service again within ``min_dwell_s`` seconds
    ceiling    never scale a service past ``max_capacity`` units
    rate       (dwell doubles as a per-service rate limit)

State lives next to the ledger as ``guardrails.json``.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass


@dataclass
class GuardVerdict:
    allowed: bool
    reason: str
    capped_value: float | None = None  # a smaller safe value, if we clamped it


class FlapGuard:
    """File-backed record of the last action time per service."""

    def __init__(self, root: str | None = None):
        self.root = root or os.path.join(os.path.dirname(__file__), "..", "..", "ledger")
        os.makedirs(self.root, exist_ok=True)
        self.path = os.path.join(self.root, "guardrails.json")

    def _load(self) -> dict:
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}

    def _save(self, data: dict) -> None:
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)

    def last_action_at(self, service: str) -> float:
        return float(self._load().get(service, {}).get("last_action_at", 0.0))

    def actions_last_hour(self, service: str, now: float | None = None) -> int:
        now = time.time() if now is None else now
        hist = (self._load().get(service, {}) or {}).get("history") or []
        return sum(1 for t in hist if now - float(t) < 3600)

    def note_action(self, service: str, action: str) -> None:
        data = self._load()
        rec = data.get(service) or {}
        now = time.time()
        hist = [t for t in (rec.get("history") or []) if now - float(t) < 7200]
        hist.append(now)
        data[service] = {"last_action_at": now, "action": action, "history": hist[-50:]}
        self._save(data)

    def check(self, service: str, action: str, *, min_dwell_s: float,
              current_capacity: float, scale_value: float, max_capacity: float,
              max_per_hour: int = 999, now: float | None = None) -> GuardVerdict:
        """Decide whether ``action`` on ``service`` is allowed right now."""
        now = time.time() if now is None else now
        # 0) action budget — hard cap on how often we touch one service
        if self.actions_last_hour(service, now) >= max_per_hour:
            return GuardVerdict(False,
                                f"anti-flap: action budget reached ({max_per_hour}/hr) for {service} — holding.")
        # 1) dwell / rate limit
        since = now - self.last_action_at(service)
        if since < min_dwell_s:
            return GuardVerdict(False,
                                f"anti-flap: acted {since:.0f}s ago (<{min_dwell_s:.0f}s dwell) — holding.")
        # 2) capacity ceiling (only relevant to scale-out)
        if action == "scale" and scale_value > 0:
            projected = current_capacity + scale_value
            if current_capacity >= max_capacity:
                return GuardVerdict(False,
                                    f"anti-flap: already at capacity ceiling ({max_capacity}) — won't scale further.")
            if projected > max_capacity:
                capped = max(0.0, max_capacity - current_capacity)
                return GuardVerdict(True,
                                    f"clamped scale to +{capped} to stay under the {max_capacity} ceiling.",
                                    capped_value=capped)
        return GuardVerdict(True, "within guardrails.")
