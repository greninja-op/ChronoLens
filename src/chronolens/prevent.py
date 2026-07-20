"""PREVENT — take a small, reversible action before the breach lands.

Every action ChronoLens takes must be undoable. That single rule is what makes
running without a human safe: a wrong guess costs you a briefly-oversized pool,
not a self-inflicted outage. Actions are applied by pulling the demo store's
admin levers.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from .config import Config


@dataclass
class Remediation:
    action: str
    params: dict
    rollback: str
    applied: bool = False
    result: dict | None = None
    error: str | None = None


def propose(forecast_service: str) -> Remediation:
    """Choose a reversible action for a predicted breach.

    For the demo store the breach is load-driven, so the fix is to **scale out**
    (add capacity) — fully reversible by scaling back down.
    """
    return Remediation(
        action="scale",
        params={"service": forecast_service, "value": 2.0},
        rollback="Scale the service back down by 2 capacity units once load subsides.",
    )


def apply(cfg: Config, rem: Remediation, timeout: float = 8.0) -> Remediation:
    """Execute the reversible action against the demo store's lever API."""
    try:
        r = httpx.post(
            f"{cfg.demo_store_url}/admin/lever",
            params={"action": rem.action, "value": rem.params.get("value", 2.0)},
            timeout=timeout,
        )
        r.raise_for_status()
        rem.result = r.json()
        rem.applied = True
    except Exception as exc:
        rem.error = f"could not apply remediation: {exc}"
    return rem


def scale_by(cfg: Config, delta: float, timeout: float = 8.0) -> dict:
    """Scale capacity by ``delta`` (used for learned pre-provisioning)."""
    try:
        r = httpx.post(f"{cfg.demo_store_url}/admin/lever",
                       params={"action": "scale", "value": delta}, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        return {"error": str(exc)}


def rollback(cfg: Config, rem: Remediation, timeout: float = 8.0) -> bool:
    """Undo a scale action (used when verification fails)."""
    if rem.action != "scale":
        return False
    try:
        httpx.post(
            f"{cfg.demo_store_url}/admin/lever",
            params={"action": "scale", "value": -rem.params.get("value", 2.0)},
            timeout=timeout,
        )
        return True
    except Exception:
        return False
