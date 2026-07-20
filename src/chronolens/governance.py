"""Governance — the trust ladder that decides *whether* ChronoLens may act.

Autonomy is earned, not assumed. Three modes:

    suggest   never acts on its own — only proposes (human-in-the-loop)
    earn      acts autonomously *once it has proven itself* with N verified
              saves on that service; until then it only suggests
    auto      always acts (the demo default, so the loop is visible end-to-end)

This keeps a wrong guess cheap early on: before ChronoLens has a track record,
it defers to a human; after it has repeatedly been right, it's allowed to move
on its own.
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import Config
from .record import Ledger


@dataclass
class Decision:
    may_act: bool
    mode: str
    proven_saves: int
    reason: str


def proven_saves_for(service: str, ledger: Ledger) -> int:
    """How many times ChronoLens has *verifiably* saved this service."""
    return sum(
        1 for c in ledger.list()
        if c.get("service") == service and c.get("outcome") == "breach avoided"
    )


def decide(cfg: Config, service: str, ledger: Ledger) -> Decision:
    """Consult the trust ladder for one service."""
    mode = cfg.autonomy
    if mode == "auto":
        return Decision(True, mode, proven_saves_for(service, ledger),
                        "autonomy=auto — acting automatically.")
    if mode == "suggest":
        return Decision(False, mode, proven_saves_for(service, ledger),
                        "autonomy=suggest — proposing only, waiting for a human to approve.")
    # "earn": autonomous once it has a proven track record on this service.
    proven = proven_saves_for(service, ledger)
    if proven >= cfg.trust_min_saves:
        return Decision(True, mode, proven,
                        f"autonomy=earn — {proven} proven saves on {service} "
                        f"(≥{cfg.trust_min_saves}); trusted to act.")
    return Decision(False, mode, proven,
                    f"autonomy=earn — only {proven}/{cfg.trust_min_saves} proven saves "
                    f"on {service}; suggesting until trust is earned.")
