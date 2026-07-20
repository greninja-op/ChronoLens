"""NOTIFY — tell a human (Slack / generic webhook) when something happened.

A prevented outage is invisible by nature, so ChronoLens announces it. Posts a
short, human-readable message to a Slack incoming webhook (or any webhook that
accepts a JSON ``{"text": ...}`` body). Fails open: no URL configured, or the
POST fails, and the loop carries on unbothered.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from .config import Config


@dataclass
class NotifyResult:
    sent: bool
    reason: str


def _emoji(outcome: str) -> str:
    return {
        "breach avoided": "✅",
        "pre-empted": "🧠",
        "escalated": "🚨",
    }.get(outcome, "ℹ️")


def build_message(*, service: str, outcome: str, action: str, eta_s: float | None,
                  p99_before: float, p99_after: float, dollars_saved: float) -> str:
    """Compose the human-readable notification text."""
    when = "now" if not eta_s else f"in ~{eta_s:.0f}s"
    lines = [
        f"{_emoji(outcome)} *ChronoLens* — {outcome} on `{service}`",
        f"• Forecast: p99 heading past SLO {when}",
        f"• Action: `{action}` (reversible)",
        f"• p99 {p99_before:.0f}ms → {p99_after:.0f}ms",
    ]
    if dollars_saved > 0:
        lines.append(f"• Cost returned on cooldown: ${dollars_saved:,.2f}")
    return "\n".join(lines)


def notify(cfg: Config, message: str, *, timeout: float = 6.0) -> NotifyResult:
    """Post ``message`` to the configured webhook. Never raises."""
    url = cfg.notify_webhook_url
    if not url:
        return NotifyResult(False, "no CHRONOLENS_WEBHOOK_URL configured")
    try:
        r = httpx.post(url, json={"text": message}, timeout=timeout)
        r.raise_for_status()
        return NotifyResult(True, "sent")
    except Exception as exc:  # fail open
        return NotifyResult(False, f"webhook post failed: {exc}")
