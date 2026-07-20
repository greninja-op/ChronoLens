"""COOLDOWN — give the capacity back once the load is over (save cost).

Scaling up to prevent a breach is only half a loop. A real closed loop also
scales *down* when the spike passes, so you're not paying for idle capacity.
ChronoLens watches the store's headroom; once demand has dropped well under
capacity for a sustained window, it scales back to baseline and records how
much capacity (cost) it returned.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from .config import Config


@dataclass
class CoolDown:
    scaled_down: bool
    capacity_before: float
    capacity_after: float
    cost_units_returned: float
    waited_s: float
    note: str


def _store_status(cfg: Config, timeout: float = 6.0) -> dict:
    return httpx.get(f"{cfg.demo_store_url}/admin/status", timeout=timeout).json()


def cool_down(cfg: Config, *, baseline: float | None = None,
              checks: int = 8, interval_s: float = 2.0,
              headroom_margin: float = 1.0) -> CoolDown:
    """Poll headroom; when the spike subsides, scale back to baseline.

    "Subsided" = capacity exceeds demand by more than ``headroom_margin`` (i.e.
    we're clearly over-provisioned). Bounded by ``checks`` polls so it never
    blocks forever; if load is still high it holds capacity and says so.
    """
    import time

    try:
        st = _store_status(cfg)
    except Exception as exc:
        return CoolDown(False, 0, 0, 0, 0, f"could not read store status: {exc}")

    cap_before = float(st.get("capacity", 0))
    base = baseline if baseline is not None else float(st.get("baseline_capacity", 2.0))
    waited = 0.0

    for i in range(max(1, checks)):
        try:
            st = _store_status(cfg)
        except Exception:
            break
        cap = float(st.get("capacity", cap_before))
        headroom = float(st.get("headroom", 0))
        # Over-provisioned and above baseline -> give capacity back.
        if headroom > headroom_margin and cap > base:
            try:
                httpx.post(f"{cfg.demo_store_url}/admin/lever",
                           params={"action": "scale", "value": base - cap}, timeout=6).raise_for_status()
                return CoolDown(
                    scaled_down=True, capacity_before=cap, capacity_after=base,
                    cost_units_returned=round(cap - base, 2), waited_s=round(waited, 1),
                    note=f"Load subsided — scaled {cap} → {base}, returned {round(cap - base, 2)} capacity units.",
                )
            except Exception as exc:
                return CoolDown(False, cap, cap, 0, round(waited, 1), f"scale-down failed: {exc}")
        if i < checks - 1:
            time.sleep(interval_s)
            waited += interval_s

    return CoolDown(False, cap_before, cap_before, 0, round(waited, 1),
                    "Load still elevated — holding extra capacity (will release when it drops).")
