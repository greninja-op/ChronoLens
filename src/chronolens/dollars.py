"""Cost model — turn abstract capacity units into real money.

The loop scales in "capacity units". Operators think in dollars. This module is
the one place that translates between the two, so cost math stays consistent
across RECORD, the ledger, the CLI, and the UI.

A capacity unit is billed per hour (``cost_per_unit_hr``). "Cost saved" is the
capacity we *returned* during COOLDOWN, valued over a nominal 1-hour window —
the money you'd have burned leaving it scaled up.
"""
from __future__ import annotations

from .config import Config

# How long a returned unit is assumed to have stayed up if we hadn't cooled it
# down. One hour is a deliberately conservative, easy-to-explain window.
BILL_WINDOW_HR = 1.0


def units_to_dollars(units: float, cfg: Config, *, window_hr: float = BILL_WINDOW_HR) -> float:
    """Value a number of capacity units in dollars over a billing window."""
    return round(max(0.0, units) * cfg.cost_per_unit_hr * window_hr, 2)


def fmt(amount: float) -> str:
    """Format a dollar amount for display."""
    return f"${amount:,.2f}"
