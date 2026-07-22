"""PREVENT — take a small, reversible action before the breach lands.

Two rules make running without a human safe:

1. **Every action is reversible.** A wrong guess costs a briefly-oversized pool
   or an isolated dependency, not a self-inflicted outage.
2. **The action fits the signal.** PREVENT doesn't always scale — it asks the
   :mod:`playbook` what's actually wrong (load / dependency / pool / memory /
   errors) and picks the matching reversible lever.

Anti-flap :mod:`guardrails` sit in front of every action so the loop can't
oscillate or scale to infinity. Actions are applied via the demo store's admin
levers.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from .config import Config
from .guardrails import FlapGuard
from .playbook import classify, play_for


@dataclass
class Remediation:
    action: str
    params: dict
    rollback: str
    why: str = ""
    signal: str = "load"
    applied: bool = False
    blocked: bool = False
    block_reason: str = ""
    result: dict | None = None
    error: str | None = None
    notes: list[str] = field(default_factory=list)


def propose(service: str, cfg: Config | None = None, *, signal: str | None = None) -> Remediation:
    """Choose a reversible action, matched to the dominant failure signal.

    Reads the signal from the playbook (a proxy for SigNoz metrics + traces) and
    maps it to a reversible lever. Falls back to scale-out when the signal is
    unknown or broadly latency-bound.
    """
    if signal is None and cfg is not None:
        signal = classify(cfg)
    play = play_for(signal or "load")
    return Remediation(
        action=play.action,
        params={"service": service, "value": play.value},
        rollback=play.rollback,
        why=play.why,
        signal=play.signal,
    )


def _store_capacity(cfg: Config, timeout: float = 6.0) -> float:
    try:
        st = httpx.get(f"{cfg.demo_store_url}/admin/status", timeout=timeout).json()
        return float(st.get("capacity", 0.0))
    except Exception:
        return 0.0


def apply(cfg: Config, rem: Remediation, *, guard: FlapGuard | None = None,
          timeout: float = 8.0) -> Remediation:
    """Execute the reversible action, after clearing anti-flap guardrails."""
    guard = guard or FlapGuard()
    value = float(rem.params.get("value", 0.0) or 0.0)
    cap = _store_capacity(cfg)

    verdict = guard.check(
        rem.params.get("service", "?"), rem.action,
        min_dwell_s=cfg.min_dwell_s, current_capacity=cap,
        scale_value=value, max_capacity=cfg.max_capacity,
        max_per_hour=getattr(cfg, "max_actions_per_hour", 999),
    )
    if not verdict.allowed:
        rem.blocked = True
        rem.block_reason = verdict.reason
        return rem
    if verdict.capped_value is not None:
        value = verdict.capped_value
        rem.params["value"] = value
        rem.notes.append(verdict.reason)

    try:
        r = httpx.post(
            f"{cfg.demo_store_url}/admin/lever",
            params={"action": rem.action, "value": value},
            timeout=timeout,
        )
        r.raise_for_status()
        rem.result = r.json()
        rem.applied = True
        guard.note_action(rem.params.get("service", "?"), rem.action)
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


# Each action's *precise* inverse lever on the demo store (no blunt full reset).
_INVERSE = {
    "scale": lambda v: ("scale", -v),
    "pool-resize": lambda v: ("pool-resize", -v),
    "circuit-break": lambda v: ("close-circuit", 0.0),
    "rollback": lambda v: ("redeploy", 0.0),
    "restart": None,  # a rolling restart is idempotent — nothing to undo
}


def rollback(cfg: Config, rem: Remediation, timeout: float = 8.0) -> bool:
    """Undo an applied action with its *precise* inverse (used when verify fails)."""
    if not rem.applied:
        return False
    inv = _INVERSE.get(rem.action)
    if inv is None:
        return False  # unknown or idempotent action — nothing to reverse
    value = float(rem.params.get("value", 0.0) or 0.0)
    action, val = inv(value)
    try:
        httpx.post(f"{cfg.demo_store_url}/admin/lever",
                   params={"action": action, "value": val}, timeout=timeout)
        return True
    except Exception:
        return False
